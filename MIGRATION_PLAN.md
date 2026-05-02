# Crypto Migration Plan

Migrate this repo from a stock trading agent system to a crypto trading agent system. The codebase is modular (vendor abstraction in `tradingagents/dataflows/`, configurable analysts, no live execution), so most work is mechanical replacement plus a few new modules.

**Scope:** advisory/analytical only — same as today. No live order placement.

**Branch:** `claude/crypto-trading-migration-jFir0` (you are already on it).

---

## Ground rules for the implementer

1. **Work in the order below.** Each phase ends in a runnable state — don't start phase N+1 until N runs end-to-end.
2. **Commit per phase** with a message like `phase 2: swap market data to ccxt`. Push after each commit.
3. **Don't add backwards-compat shims.** Stocks are gone. Delete code, don't gate it behind flags.
4. **Don't invent providers.** Use the exact providers named below. If one is unreachable, stop and ask.
5. **Keep the LangGraph orchestration layer intact** — `graph/setup.py`, `graph/propagation.py`, `graph/reflection.py` structure should not change. Only inputs/outputs change.
6. **Tests in `tests/`** must pass after each phase. Update fixtures as you go; don't leave broken tests "for later".

---

## Architectural decisions (pre-decided so you don't have to)

| Decision | Choice | Rationale |
|---|---|---|
| Symbol format | `BASE/QUOTE` with optional `venue:` prefix, e.g. `binance:BTC/USDT`, `BTC/USD` | ccxt-native, matches exchange UIs |
| Default venue | `binance` | Deepest liquidity, ccxt support, free public API |
| Default quote | `USDT` | Standard for alts; `USD` only for BTC/ETH on Coinbase |
| Market data | `ccxt` (unified across exchanges) | Single dependency, swappable venue |
| Reference prices | `coingecko` (free tier) | Market cap, dominance, no key needed for basics |
| News | `cryptopanic` (free tier, requires token) | Aggregates major crypto news outlets |
| On-chain | `coinglass` REST API for derivatives (funding, OI, liquidations); skip Glassnode for v1 (paywalled) | Free tier covers what we need |
| Tokenomics | `defillama` (free, no key) for TVL/protocol revenue; CoinGecko for supply/unlocks | Free, comprehensive |
| Social | Keep agent abstraction; data source = CryptoPanic sentiment + LunarCrush (free tier, key required) | Real signals, no scraping fragility |
| Benchmark for reflection | BTC/USDT (configurable) | Crypto's "SPY" |
| Time resolution | Daily by default; allow `1h`/`4h`/`1d` via config | Reflection windows can stay 5d initially |
| Timezone | UTC everywhere | No market hours, avoid TZ bugs |
| Removed agents | Fundamentals Analyst | No 10-Ks |
| New agents | Tokenomics Analyst, On-Chain/Derivatives Analyst | Crypto-native signals |

If a free-tier API returns 401/403 or quota errors, surface a clear error and continue with the other analysts — do not crash the whole graph.

---

## Phase 0 — Prep (no code changes)

- Read these files end-to-end before starting:
  - `tradingagents/default_config.py`
  - `tradingagents/dataflows/interface.py` (vendor routing)
  - `tradingagents/dataflows/utils.py`
  - `tradingagents/agents/utils/agent_utils.py` (look at `build_instrument_context`)
  - `tradingagents/graph/trading_graph.py` (especially `_fetch_returns` ~line 191 and `_resolve_pending_entries` ~line 229)
  - `cli/main.py` (the user-flow loop, ~line 463–551)
  - `cli/utils.py` (`get_ticker`)
  - One analyst end-to-end: `tradingagents/agents/analysts/market_analyst.py`
- Run `python main.py` once on the existing stock setup to confirm baseline works (or note what's broken before you start).
- Check `tests/` and run them: `pytest tests/`. Note which pass on `main`.

---

## Phase 1 — Symbol model & config rename (no behavior change yet)

Goal: introduce `(base, quote, venue)` plumbing without breaking stock flow. After this phase, stocks still work.

1. **Create `tradingagents/dataflows/symbols.py`:**
   - `class Instrument(NamedTuple)`: `base: str`, `quote: str`, `venue: str | None`
   - `def parse_symbol(s: str) -> Instrument`: accepts `BTC/USDT`, `binance:BTC/USDT`, `BTC-USD` (normalize `-` → `/`); raise `ValueError` with examples on bad input.
   - `def format_symbol(i: Instrument, style: str = "ccxt") -> str`: `"BTC/USDT"` or `"binance:BTC/USDT"`.
2. **Rewrite `tradingagents/agents/utils/agent_utils.py:build_instrument_context()`** to consume `Instrument` and emit the same prompt-context string (just with crypto-correct examples).
3. **Update `tradingagents/dataflows/utils.py:safe_ticker_component()`** to allow `/`, `-`, digits-leading symbols. Keep length cap.
4. **In state**, rename `"company_of_interest"` → `"instrument"` everywhere. Grep before changing — touches `graph/`, `agents/`, possibly `cli/`. Do a single rename commit.
5. **Add tests** in `tests/test_symbols.py` covering parse round-trips and bad inputs.

End state: `pytest` green; `python main.py` may break on stock symbol — that's fine starting next phase.

---

## Phase 2 — Swap market data to ccxt

Goal: Market Analyst works end-to-end on `BTC/USDT`. All other analysts can be temporarily disabled.

1. **Add dependencies** to `pyproject.toml` and `requirements.txt`: `ccxt`, `pycoingecko`. Remove `yfinance`, `stockstats` (we'll reimplement indicators via `pandas_ta` — also add it). Remove `backtrader` (unused).
2. **Create `tradingagents/dataflows/ccxt_market_data.py`:**
   - `def get_ohlcv(instrument: Instrument, timeframe: str, since: datetime, until: datetime) -> pd.DataFrame`
   - Use `ccxt.binance()` (or `getattr(ccxt, instrument.venue)()` if specified).
   - Cache to disk under `~/.tradingagents/cache/ccxt/<venue>/<base>_<quote>_<tf>.parquet` keyed by date range. Re-use existing cache pattern if there is one in `dataflows/`.
   - Handle rate limits with exponential backoff (ccxt has `enableRateLimit=True` — turn it on).
3. **Create `tradingagents/dataflows/coingecko.py`:**
   - `def get_market_summary(base: str) -> dict`: market cap, 24h vol, dominance, ATH/ATL, supply.
   - Free tier, no auth.
4. **Create `tradingagents/dataflows/indicators.py`:** thin wrapper over `pandas_ta` exposing the same indicator names previously used (`rsi`, `macd`, `sma_20`, `ema_12`, `bbands`). Match the return shape `stockstats_utils` provided so `market_analyst.py` is minimally changed.
5. **Delete:** `tradingagents/dataflows/y_finance.py`, `yfinance_news.py`, `alpha_vantage_*.py` (5 files), `stockstats_utils.py`. Don't leave imports dangling — fix them.
6. **Update `tradingagents/default_config.py`:**
   - Rename categories: `core_stock_apis` → `market_data`, keep `technical_indicators`, drop `fundamental_data`, rename `news_data` (keep name).
   - Add `onchain_data`, `derivatives_data`, `tokenomics_data` categories with placeholder vendors (filled in later phases).
   - Default `market_data` vendor: `"ccxt"`. Default `technical_indicators`: `"pandas_ta"`.
7. **Update `tradingagents/dataflows/interface.py:route_to_vendor()`** to know about new vendor names.
8. **Update `tradingagents/agents/utils/core_stock_tools.py`** (rename file → `market_data_tools.py`):
   - `get_stock_data` → `get_market_data` (returns OHLCV from ccxt).
   - `get_indicators` — same name, points at new indicators module.
9. **Update `tradingagents/agents/analysts/market_analyst.py`** to use new tool names.
10. **In `cli/utils.py:get_ticker()`** update prompt copy and examples to crypto pairs (`BTC/USDT`, `ETH/USD`, `SOL/USDT`, `binance:DOGE/USDT`). Validate via `parse_symbol()`.
11. **`cli/main.py`** — disable selection of fundamentals/news/social analysts for now (only allow `market`). Re-enable as later phases land.
12. **Smoke test:** `python main.py` with `ta.propagate("BTC/USDT", "2026-05-02")` should produce a Market Analyst report and a final decision (with degraded research, since other analysts are off).

Commit + push.

---

## Phase 3 — News & social data

1. **Add `tradingagents/dataflows/cryptopanic.py`:**
   - `def get_news(base: str, since: datetime, until: datetime, limit: int = 50) -> list[dict]`
   - Requires `CRYPTOPANIC_TOKEN` env var. If missing, return `[]` and log a warning.
   - Map response to `{title, url, source, published_at, sentiment_label}`.
2. **Add `tradingagents/dataflows/lunarcrush.py`:**
   - `def get_social_metrics(base: str) -> dict`: galaxy_score, alt_rank, social_volume, sentiment.
   - Requires `LUNARCRUSH_API_KEY`. Same fallback as above.
3. **Update `tradingagents/agents/utils/news_data_tools.py`:**
   - Drop `get_insider_transactions` entirely.
   - `get_news`, `get_global_news` → backed by CryptoPanic. "Global" = no `currencies` filter.
4. **Update `tradingagents/agents/analysts/news_analyst.py`:** remove insider tool from its tool list. Update system prompt to mention "regulatory developments (SEC/CFTC actions, ETF flows, exchange listings/delistings)" as items to flag.
5. **Update `tradingagents/agents/analysts/social_media_analyst.py`:** wire it to a new `get_social_metrics` tool. Update system prompt to mention crypto-native sources (Twitter/X, Reddit r/CryptoCurrency, Discord, on-chain "smart money" signals via LunarCrush).
6. **Re-enable news + social in `cli/main.py` analyst selection.**
7. Smoke test with `BTC/USDT` and `ETH/USDT`.

Commit + push.

---

## Phase 4 — Tokenomics analyst (replaces Fundamentals)

1. **Add `tradingagents/dataflows/defillama.py`:**
   - `def get_protocol_tvl(slug: str) -> dict`: TVL, change_24h, change_7d, chains.
   - `def get_protocol_revenue(slug: str) -> dict | None`: 24h/7d/30d revenue if available.
   - No auth required.
   - Maintain a small mapping `BASE → defillama_slug` in the file (e.g. `UNI → uniswap`, `AAVE → aave`, `LDO → lido`). Unmapped → return `None`, don't crash.
2. **Extend `tradingagents/dataflows/coingecko.py`:**
   - `def get_tokenomics(base: str) -> dict`: circulating_supply, total_supply, max_supply, fdv, ath, ath_change_pct.
3. **Create `tradingagents/agents/utils/tokenomics_data_tools.py`** exposing `get_tokenomics`, `get_protocol_metrics`.
4. **Replace `tradingagents/agents/analysts/fundamentals_analyst.py`** with `tokenomics_analyst.py`. Keep the same class shape (LangGraph node signature) so `graph/setup.py` integration is one-line. System prompt: "You analyze token supply dynamics (inflation schedule, unlocks, FDV vs MCAP), protocol fundamentals (TVL, revenue, fees), and on-chain holder distribution. You do NOT analyze traditional financial statements — these don't exist for crypto."
5. **Update `tradingagents/agents/utils/agent_states.py`** (or wherever the report state keys live): rename `fundamentals_report` → `tokenomics_report`. Grep first; this likely touches `graph/setup.py` and `cli/main.py` MessageBuffer.
6. **Update `cli/main.py`** analyst selection: rename "fundamentals" → "tokenomics".
7. **Update `cli/models.py:AnalystType`** enum.
8. Smoke test: full graph with all four analysts on `ETH/USDT`.

Commit + push.

---

## Phase 5 — On-chain / derivatives analyst (NEW)

1. **Add `tradingagents/dataflows/coinglass.py`:**
   - `def get_funding_rate(instrument: Instrument) -> dict`: current rate, 8h history.
   - `def get_open_interest(instrument: Instrument) -> dict`: total OI, 24h change, by exchange.
   - `def get_long_short_ratio(instrument: Instrument) -> dict`
   - `def get_liquidations(instrument: Instrument, window: str = "24h") -> dict`: total long/short liquidations.
   - Free tier rate limit: ~30 req/min. Cache aggressively (TTL 5 min).
   - If `COINGLASS_API_KEY` missing: return empty dicts, log warning.
2. **Create `tradingagents/agents/utils/derivatives_data_tools.py`** exposing the four functions above.
3. **Create `tradingagents/agents/analysts/derivatives_analyst.py`:**
   - Same node shape as other analysts.
   - Tools: the four above.
   - System prompt focus: "You analyze derivatives market structure: funding rates (positive = longs paying = crowded long), open interest trends, long/short imbalance, recent liquidation cascades. Flag funding > 0.1% per 8h or < -0.05% as extreme. OI rising with price = healthy trend; OI rising with price falling = bearish (shorts piling in)."
4. **Wire into `graph/setup.py`** as an optional analyst (same pattern as the others).
5. **Add to `cli/models.py:AnalystType`** and `cli/main.py` selection menu.
6. **Add report key** `derivatives_report` to state and to MessageBuffer in `cli/main.py`.
7. Smoke test on a perp-tradeable pair (`BTC/USDT`).

Commit + push.

---

## Phase 6 — Reflection & benchmark

1. **`tradingagents/graph/trading_graph.py:_fetch_returns()` (~line 191):**
   - Replace SPY benchmark fetch with BTC/USDT via ccxt.
   - Add config key `reflection_benchmark` (default `"BTC/USDT"`); allow `"none"` to skip alpha calc.
   - For BTC itself, benchmark against ETH/USDT (or skip alpha — your call, document it).
   - Use the same `ccxt_market_data.get_ohlcv` you built in phase 2.
2. **`_resolve_pending_entries()` (~line 229):** ensure date math uses UTC and that "5 trading days later" becomes "5 calendar days later" (crypto = no holidays).
3. **No prompt changes required** in `reflection.py` — it's symbol-agnostic. Verify by reading.
4. Run a full propagate + verify a memory log entry gets written and resolved correctly when you re-run with a date 6+ days in the past.

Commit + push.

---

## Phase 7 — Risk module retuning

The risk debaters' prompts assume equity volatility. Crypto needs recalibration.

1. Files: `tradingagents/agents/risk_mgmt/aggressive_debator.py`, `neutral_debator.py`, `conservative_debator.py`.
2. Update each system prompt to:
   - Acknowledge crypto's higher daily vol (5–10× equities).
   - Reference crypto-specific risks: smart contract exploits, exchange insolvency, regulatory action, stablecoin depegs, validator slashing.
   - Aggressive: comfortable with 2–5× leverage on majors, willing to size up on alts.
   - Conservative: spot-only, max 2–5% per alt position, prefers BTC/ETH, watches for funding extremes.
   - Neutral: balances the two.
3. **`tradingagents/agents/managers/portfolio_manager.py`** — extend `PortfolioDecision` schema with optional `leverage: float = 1.0` and `stop_loss_pct: float | None`. Update the manager's prompt to fill these.
4. **`tradingagents/agents/trader/trader.py`** — update prompt to think in fractional units (you can buy 0.0023 BTC) and to express size as % of portfolio rather than share count.
5. Smoke test: confirm new fields appear in final decision output and CLI displays them.

Commit + push.

---

## Phase 8 — Tests, docs, polish

1. **`tests/`:** update every fixture using stock symbols. Mock ccxt with `unittest.mock` returning canned OHLCV DataFrames. Add tests for:
   - `parse_symbol` round-trips
   - `ccxt_market_data.get_ohlcv` cache hit/miss
   - Each new dataflow module with an HTTP mock (use `responses` or `respx`)
   - Tokenomics analyst node produces non-empty report given mocked data
2. **`README.md`:** rewrite intro, examples, env var list, supported pairs section. Replace any stock screenshots/examples.
3. **`main.py`:** change example to `ta.propagate("BTC/USDT", "2026-05-02")`.
4. **`CHANGELOG.md`:** add a top entry "Migrated from stock trading to crypto trading. Breaking change."
5. **`cli/static/`:** if the ASCII art or welcome screen says "stocks" anywhere, update it.
6. **`pyproject.toml`:** consider renaming the package or at least the description. Project name `tradingagents` can stay; update `description` field.
7. Run `pytest tests/` — must be green.
8. Run `python main.py` end-to-end on `BTC/USDT` and on `SOL/USDT` (alt with derivatives data) and on `LDO/USDT` (alt with TVL data via DeFiLlama).

Commit + push. Done.

---

## Env vars to document in README

| Var | Required? | Used by |
|---|---|---|
| `OPENAI_API_KEY` (or other LLM provider key) | yes | LLM |
| `CRYPTOPANIC_TOKEN` | recommended | News analyst |
| `LUNARCRUSH_API_KEY` | recommended | Social analyst |
| `COINGLASS_API_KEY` | recommended | Derivatives analyst |
| `COINGECKO_API_KEY` | optional (free tier works without) | Tokenomics |

If a recommended var is missing, the corresponding analyst should still run but produce a "data unavailable" note rather than crash.

---

## Files that will be deleted

- `tradingagents/dataflows/y_finance.py`
- `tradingagents/dataflows/yfinance_news.py`
- `tradingagents/dataflows/alpha_vantage_common.py`
- `tradingagents/dataflows/alpha_vantage_market_data.py`
- `tradingagents/dataflows/alpha_vantage_indicators.py`
- `tradingagents/dataflows/alpha_vantage_fundamentals.py`
- `tradingagents/dataflows/alpha_vantage_news.py`
- `tradingagents/dataflows/stockstats_utils.py`
- `tradingagents/agents/analysts/fundamentals_analyst.py` (replaced by `tokenomics_analyst.py`)
- `tradingagents/agents/utils/fundamental_data_tools.py` (replaced by `tokenomics_data_tools.py`)

Don't leave dead imports. Don't leave `# removed:` comments. Just delete.

---

## Anti-goals — do NOT do these

- Do not add a "stocks vs crypto" mode toggle. The repo is crypto now.
- Do not add live order execution.
- Do not introduce a new orchestration framework. Keep LangGraph.
- Do not add a backtesting engine (backtrader is being removed). Reflection on past trades is sufficient.
- Do not add caching layers beyond what's already in `dataflows/` (Redis is fine if already wired, otherwise disk parquet).
- Do not write multi-paragraph docstrings or design docs beyond this file.

---

## When to stop and ask

- A free-tier API requires a credit card / payment to issue a key.
- A symbol the user requests doesn't exist on Binance and isn't on Coinbase either.
- Reflection benchmark logic produces obviously wrong alphas (e.g., 1000%+).
- Any test you can't make pass after a reasonable attempt — flag it, don't `xfail` silently.

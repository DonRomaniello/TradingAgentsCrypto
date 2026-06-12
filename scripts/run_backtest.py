"""Run a full-pipeline backtest over a historical date range.

For each decision date the complete agent graph runs (analysts → debate →
trader → risk → portfolio manager), the resulting 5-tier rating is mapped to
a long-only exposure, and the equity curve is simulated against daily closes
with trading costs. Decisions persist to a JSONL file as they complete, so an
interrupted run resumes without re-paying for finished dates.

Usage:
    OPENAI_API_KEY=... python scripts/run_backtest.py BTC-USD 2026-03-01 2026-06-01
    python scripts/run_backtest.py ETH-USD 2026-01-01 2026-06-01 \
        --every 7 --cost-bps 10 --provider openai --quick-model gpt-5.4-mini

Cost warning: every decision date is a full multi-agent run (~15-25 LLM
calls). A year of weekly decisions is ~50 runs. Start small.

Honesty warning: news and fundamentals are not point-in-time for historical
dates, and the LLM may have post-hoc knowledge of the period. The report
lists these caveats; results on dates before the model's knowledge cutoff
are optimistic at best. See the "Data integrity caveats" section.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tradingagents.backtest import BacktestEngine
from tradingagents.backtest.report import save_report
from tradingagents.default_config import DEFAULT_CONFIG


def build_blind_decide_fn(args):
    """Anonymized technicals-only decision source (memorization-resistant)."""
    from tradingagents.backtest.blind import make_blind_decide_fn
    from tradingagents.llm_clients import create_llm_client

    config = DEFAULT_CONFIG.copy()
    provider = args.provider or config["llm_provider"]
    model = args.quick_model or config["quick_think_llm"]
    llm = create_llm_client(provider=provider, model=model).get_llm()
    return make_blind_decide_fn(llm, lookback_days=args.lookback)


def build_decide_fn(args):
    """Wrap TradingAgentsGraph.propagate as a (ticker, date) -> rating callable."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = DEFAULT_CONFIG.copy()
    if args.provider:
        config["llm_provider"] = args.provider
    if args.deep_model:
        config["deep_think_llm"] = args.deep_model
    if args.quick_model:
        config["quick_think_llm"] = args.quick_model
    # The memory log would let later backtest dates "learn" from earlier
    # outcomes within the same run — legitimate — but a pre-existing log from
    # live usage could leak future knowledge into early dates. Use a
    # backtest-scoped log next to the decisions file.
    config["memory_log_path"] = str(
        Path(args.out) / f"backtest_memory_{args.ticker}.md"
    )

    graph = TradingAgentsGraph(selected_analysts=args.analysts, config=config)

    def decide(ticker: str, date: str) -> str:
        _, rating = graph.propagate(ticker, date)
        return rating

    return decide


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticker", help="Instrument, e.g. BTC-USD")
    parser.add_argument("start", help="Start date yyyy-mm-dd")
    parser.add_argument("end", help="End date yyyy-mm-dd")
    parser.add_argument("--every", type=int, default=7, help="Calendar days between decisions (default 7)")
    parser.add_argument("--cost-bps", type=float, default=10.0, help="Cost per unit turnover in bps (default 10)")
    parser.add_argument("--out", default="backtests", help="Output directory (default ./backtests)")
    parser.add_argument("--provider", default=None, help="LLM provider override")
    parser.add_argument("--deep-model", default=None, help="Deep-think model override")
    parser.add_argument("--quick-model", default=None, help="Quick-think model override")
    parser.add_argument(
        "--analysts", nargs="+", default=["market", "social", "news", "fundamentals"],
        help="Analysts to include (default: all four)",
    )
    parser.add_argument(
        "--blind", action="store_true",
        help="Anonymized technicals-only mode: the LLM never sees the ticker, "
             "dates, or absolute prices, so it cannot recall the asset's "
             "history. One LLM call per decision (cheap) and memorization-"
             "resistant, at the cost of excluding news/fundamentals/sentiment.",
    )
    parser.add_argument(
        "--lookback", type=int, default=180,
        help="Bars of anonymized history shown in --blind mode (default 180)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    out_dir = Path(args.out)
    decide_fn = build_blind_decide_fn(args) if args.blind else build_decide_fn(args)
    mode_tag = "blind_" if args.blind else ""
    engine = BacktestEngine(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        cadence_days=args.every,
        cost_bps=args.cost_bps,
        decide_fn=decide_fn,
        decisions_path=out_dir / f"{mode_tag}decisions_{args.ticker}_{args.start}_{args.end}.jsonl",
    )

    result = engine.run()
    if args.blind:
        result.warnings.insert(
            0,
            "BLIND TECHNICAL MODE: the model saw only anonymized, rebased "
            "price/indicator data (no ticker, dates, news, or fundamentals). "
            "Results are memorization-resistant and measure technical "
            "judgment only.",
        )
    md_path, json_path = save_report(result, out_dir / "blind" if args.blind else out_dir)

    m = result.metrics
    print(f"\nBacktest complete: {args.ticker} {args.start} → {args.end}")
    print(f"  Strategy return : {m['total_return']:+.2%}")
    print(f"  Buy & hold      : {m['buy_hold_return']:+.2%}")
    print(f"  Excess          : {m['excess_vs_buy_hold']:+.2%}")
    hit = f"{m['hit_rate']:.0%}" if m["hit_rate"] is not None else "n/a"
    print(f"  Hit rate        : {hit} ({m['n_directional']} directional decisions)")
    print(f"  Max drawdown    : {m['max_drawdown']:+.2%} (B&H {m['buy_hold_max_drawdown']:+.2%})")
    print(f"\nReports: {md_path}\n         {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

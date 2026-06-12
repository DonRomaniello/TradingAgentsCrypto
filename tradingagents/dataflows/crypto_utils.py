"""Crypto-native market data from free, key-less public APIs.

Three signals that matter for crypto and have no equity analogue:

- **Funding rates** (Binance USDT-perp): the cost of holding leveraged longs
  vs shorts. Persistent positive funding = crowded longs; deeply negative =
  crowded shorts. Historical endpoint, so backtest-safe.
- **Open interest** (Binance futures): leverage building up or flushing out.
  Binance only serves ~30 days of daily history.
- **Fear & Greed index** (alternative.me): daily crowd-sentiment composite,
  full history available, backtest-safe.

All functions return formatted strings (the tool-output convention used by
the rest of dataflows) and degrade to an explanatory message on API failure
rather than raising into the agent loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

_TIMEOUT = 10

_BINANCE_FAPI = "https://fapi.binance.com"
_OKX_API = "https://www.okx.com"
_FNG_URL = "https://api.alternative.me/fng/"

# Quote suffixes that map onto Binance USDT-margined perpetuals.
_USD_QUOTES = ("-USD", "-USDT", "-USDC")


def binance_perp_symbol(ticker: str) -> str | None:
    """Map a yfinance crypto pair to its Binance USDT-perp symbol.

    BTC-USD / BTC-USDT / BTC-USDC -> BTCUSDT. Pairs quoted in other
    currencies have no USDT perp mapping and return None.
    """
    upper = ticker.upper()
    for suffix in _USD_QUOTES:
        if upper.endswith(suffix):
            return upper[: -len(suffix)] + "USDT"
    return None


def _to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _binance_funding(symbol: str, start_ms: int, end_ms: int) -> list[float]:
    resp = requests.get(
        f"{_BINANCE_FAPI}/fapi/v1/fundingRate",
        params={"symbol": symbol, "startTime": start_ms, "endTime": end_ms, "limit": 1000},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return [float(r["fundingRate"]) for r in resp.json()]


def _okx_funding(symbol: str, start_ms: int, end_ms: int) -> list[float]:
    # BTCUSDT -> BTC-USDT-SWAP. `after` paginates to records older than ts.
    inst_id = f"{symbol[:-4]}-USDT-SWAP"
    resp = requests.get(
        f"{_OKX_API}/api/v5/public/funding-rate-history",
        params={"instId": inst_id, "after": end_ms, "limit": 100},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    rows = resp.json().get("data", [])
    # OKX returns newest-first; reorder oldest-first and bound the window.
    return [
        float(r["fundingRate"])
        for r in reversed(rows)
        if start_ms <= int(r["fundingTime"]) <= end_ms
    ]


def get_funding_rates(ticker: str, curr_date: str, look_back_days: int = 7) -> str:
    """Historical funding rates for the ticker's USDT perpetual.

    Date-bounded server-side, so historical runs see only data available at
    ``curr_date`` (no look-ahead). Tries Binance first, then OKX (Binance
    geo-blocks some regions with HTTP 451).
    """
    symbol = binance_perp_symbol(ticker)
    if not symbol:
        return (
            f"No USDT-perpetual mapping for {ticker}; funding rates unavailable "
            "for pairs not quoted in USD/USDT/USDC."
        )
    end_ms = _to_ms(curr_date) + 24 * 3600 * 1000  # include curr_date itself
    start_ms = end_ms - (look_back_days + 1) * 24 * 3600 * 1000

    rates, errors = [], []
    for fetch in (_binance_funding, _okx_funding):
        try:
            rates = fetch(symbol, start_ms, end_ms)
            if rates:
                break
        except Exception as e:
            errors.append(str(e))

    if not rates:
        detail = f" ({'; '.join(errors)})" if errors else ""
        return (
            f"No funding rate data for {symbol} in the {look_back_days} days "
            f"before {curr_date}{detail}."
        )
    avg = sum(rates) / len(rates)
    latest = rates[-1]
    # Funding settles every 8h -> annualised approximation
    annualised = avg * 3 * 365
    lines = [
        f"## {symbol} perpetual funding rates ({look_back_days}d window ending {curr_date})",
        f"- Latest 8h funding rate: {latest:+.4%}",
        f"- Average 8h funding rate: {avg:+.4%} (≈{annualised:+.1%} annualised)",
        f"- Settlements in window: {len(rates)}; min {min(rates):+.4%}, max {max(rates):+.4%}",
        "",
        "Interpretation: persistently positive funding means longs pay shorts "
        "(crowded long positioning, squeeze risk on downside); negative funding "
        "means crowded shorts (squeeze risk on upside). Near-zero is neutral.",
    ]
    return "\n".join(lines)


def get_open_interest(ticker: str, curr_date: str) -> str:
    """Daily open-interest history for the ticker's USDT perpetual.

    Binance serves only ~30 days of OI history; for older ``curr_date`` the
    data is reported as unavailable rather than substituting current values
    (which would be look-ahead bias).
    """
    symbol = binance_perp_symbol(ticker)
    if not symbol:
        return (
            f"No USDT-perpetual mapping for {ticker}; open interest unavailable "
            "for pairs not quoted in USD/USDT/USDC."
        )
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    cutoff_ms = int((curr_dt + timedelta(days=1)).timestamp() * 1000)

    rows, errors = [], []
    # Binance first, then OKX (Binance geo-blocks some regions with HTTP 451).
    # Both are normalised to [(timestamp_ms, oi_notional_usd), ...].
    try:
        resp = requests.get(
            f"{_BINANCE_FAPI}/futures/data/openInterestHist",
            params={"symbol": symbol, "period": "1d", "limit": 30},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        rows = [
            (int(r["timestamp"]), float(r["sumOpenInterestValue"]))
            for r in resp.json()
        ]
    except Exception as e:
        errors.append(str(e))
    if not rows:
        try:
            resp = requests.get(
                f"{_OKX_API}/api/v5/rubik/stat/contracts/open-interest-volume",
                params={"ccy": symbol[:-4], "period": "1D"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            rows = sorted(
                (int(ts), float(oi))
                for ts, oi, _vol in resp.json().get("data", [])
            )
        except Exception as e:
            errors.append(str(e))

    if not rows and errors:
        return f"Open interest data unavailable for {symbol}: {'; '.join(errors)}"

    rows = [r for r in rows if r[0] <= cutoff_ms]
    if not rows:
        return (
            f"No open interest history for {symbol} at {curr_date} "
            "(Binance serves only ~30 days; older dates have no data — do not "
            "infer positioning from current values)."
        )

    first_oi = rows[0][1]
    last_oi = rows[-1][1]
    change = (last_oi - first_oi) / first_oi if first_oi else 0.0
    lines = [
        f"## {symbol} perpetual open interest (daily, ending {curr_date})",
        f"- Latest OI notional: ${last_oi:,.0f}",
        f"- Change over available window ({len(rows)} days): {change:+.1%}",
        "",
        "Interpretation: rising OI with rising price = new longs (trend has fuel "
        "but is increasingly leveraged); rising OI with falling price = new shorts; "
        "falling OI = positions closing / deleveraging.",
    ]
    return "\n".join(lines)


def get_fear_greed_index(curr_date: str, look_back_days: int = 14) -> str:
    """Crypto Fear & Greed index history ending at ``curr_date``.

    The API returns the full daily history, so values are filtered to the
    window ending at ``curr_date`` — safe for historical runs.
    """
    try:
        resp = requests.get(
            _FNG_URL, params={"limit": 0, "format": "json"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        rows = resp.json().get("data", [])
    except Exception as e:
        return f"Fear & Greed index unavailable: {e}"

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_dt = curr_dt - timedelta(days=look_back_days)
    window = []
    for r in rows:
        ts = datetime.fromtimestamp(int(r["timestamp"]), tz=timezone.utc)
        if start_dt <= ts <= curr_dt + timedelta(days=1):
            window.append((ts, int(r["value"]), r.get("value_classification", "")))
    if not window:
        return f"No Fear & Greed data in the {look_back_days} days before {curr_date}."

    window.sort(key=lambda x: x[0])
    values = [v for _, v, _ in window]
    latest_ts, latest_val, latest_cls = window[-1]
    lines = [
        f"## Crypto Fear & Greed index ({look_back_days}d window ending {curr_date})",
        f"- Latest ({latest_ts.date()}): {latest_val} ({latest_cls})",
        f"- Window average: {sum(values) / len(values):.0f}; min {min(values)}, max {max(values)}",
        "- Daily values (oldest first): "
        + ", ".join(f"{ts.date()}={v}" for ts, v, _ in window),
        "",
        "Interpretation: 0-24 extreme fear (historically contrarian-bullish), "
        "25-49 fear, 50-74 greed, 75-100 extreme greed (crowded, correction-prone).",
    ]
    return "\n".join(lines)

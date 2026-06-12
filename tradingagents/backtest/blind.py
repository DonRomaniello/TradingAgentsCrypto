"""Blind technical decision source: anonymized, memorization-resistant ratings.

An LLM backtested on dates before its knowledge cutoff can simply *remember*
what Bitcoin did, making results meaningless. This module strips everything
the model could use to recall the asset or period:

- no ticker, asset name, or asset class beyond "a 24/7-traded asset"
- no calendar dates — bars are labelled by relative offset (day -179 .. day 0)
- no absolute price levels — closes are rebased to 100 at the window start,
  volume to a mean of 100

What remains is pure shape: trend, momentum, volatility, volume — so the
rating measures whether the model's *technical judgment* adds value, not
whether it has seen the chart before. The trade-off is explicit: news,
fundamentals, funding and sentiment are excluded, because any of them would
de-anonymize the asset.

Indicators are computed here with plain pandas (SMA/EMA/RSI/MACD/Bollinger/
ATR) on the rebased series; all are scale-invariant or rebased consistently,
so anonymization does not distort them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

import pandas as pd

from tradingagents.agents.utils.rating import RATINGS_5_TIER, parse_rating

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 180
# Daily bars shown verbatim for the most recent month; older history is
# summarized weekly to keep the prompt compact.
RECENT_DAILY_BARS = 30

BLIND_SYSTEM_PROMPT = (
    "You are a technical analyst rating an anonymized, 24/7-traded asset. "
    "You are given a price history rebased to 100 at the window start, with "
    "bars labelled by relative day (day 0 = today). You know nothing else "
    "about the asset, and you must not speculate about its identity.\n\n"
    "Weigh trend (SMAs, structure of highs/lows), momentum (RSI, MACD), "
    "volatility (Bollinger position, ATR), and volume behaviour. Commit to a "
    "directional view when the evidence supports one; reserve Hold for "
    "genuinely mixed pictures.\n\n"
    "Respond with 2-4 sentences of reasoning, then a final line of exactly:\n"
    "Rating: <one of " + " / ".join(RATINGS_5_TIER) + ">"
)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["Close"].shift()
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def prepare_blind_view(
    ohlcv: pd.DataFrame, curr_date: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS
) -> str:
    """Render an anonymized technical snapshot for the window ending curr_date.

    ``ohlcv`` must have Open/High/Low/Close/Volume columns and a (tz-naive or
    tz-aware) DatetimeIndex; only bars at or before ``curr_date`` are used, so
    the view is look-ahead-safe by construction.
    """
    df = ohlcv.copy()
    idx = df.index.tz_localize(None) if getattr(df.index, "tz", None) else df.index
    df.index = idx.normalize()
    cutoff = pd.Timestamp(curr_date)
    df = df[df.index <= cutoff].tail(lookback_days)
    if len(df) < 30:
        raise ValueError(
            f"Need at least 30 bars before {curr_date}, got {len(df)}"
        )

    # Anonymize scale: closes rebased to 100 at window start, volume to mean 100.
    base = float(df["Close"].iloc[0])
    vol_base = float(df["Volume"].mean()) or 1.0
    scaled = df.copy()
    for col in ("Open", "High", "Low", "Close"):
        scaled[col] = df[col] / base * 100
    scaled["Volume"] = df["Volume"] / vol_base * 100

    close = scaled["Close"]
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(min(200, len(close))).mean()
    ema10 = close.ewm(span=10, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    rsi = _rsi(close)
    boll_mid = close.rolling(20).mean()
    boll_std = close.rolling(20).std()
    atr = _atr(scaled)

    n = len(scaled)
    last = close.iloc[-1]

    def _day(i: int) -> int:
        return i - (n - 1)  # day 0 = most recent bar

    lines = [
        "## Anonymized asset — technical snapshot (close rebased to 100 at day "
        f"{_day(0)}, volume rebased to mean 100)",
        "",
        "### Indicator snapshot (day 0)",
        f"- Close: {last:.1f} ({(last / close.iloc[0] - 1):+.1%} over the window)",
        f"- 10 EMA: {ema10.iloc[-1]:.1f} | 50 SMA: {sma50.iloc[-1]:.1f} | "
        f"{min(200, n)} SMA: {sma200.iloc[-1]:.1f}",
        f"- RSI(14): {rsi.iloc[-1]:.0f}",
        f"- MACD: {macd.iloc[-1]:+.2f} vs signal {macd_signal.iloc[-1]:+.2f}",
        f"- Bollinger(20): mid {boll_mid.iloc[-1]:.1f}, "
        f"upper {boll_mid.iloc[-1] + 2 * boll_std.iloc[-1]:.1f}, "
        f"lower {boll_mid.iloc[-1] - 2 * boll_std.iloc[-1]:.1f}",
        f"- ATR(14): {atr.iloc[-1]:.2f} ({atr.iloc[-1] / last:.1%} of price)",
        "",
        "### Weekly history (oldest first; close / RSI / relative volume)",
    ]
    older = scaled.iloc[: n - RECENT_DAILY_BARS]
    for start in range(0, len(older), 7):
        chunk_idx = range(start, min(start + 7, len(older)))
        i_last = chunk_idx[-1]
        lines.append(
            f"- days {_day(chunk_idx[0])} to {_day(i_last)}: "
            f"close {close.iloc[i_last]:.1f}, RSI {rsi.iloc[i_last]:.0f}, "
            f"vol {scaled['Volume'].iloc[list(chunk_idx)].mean():.0f}"
        )

    lines += ["", "### Daily bars (last 30 days; day / close / RSI / volume)"]
    for i in range(max(0, n - RECENT_DAILY_BARS), n):
        lines.append(
            f"- day {_day(i)}: close {close.iloc[i]:.1f}, "
            f"RSI {rsi.iloc[i]:.0f}, vol {scaled['Volume'].iloc[i]:.0f}"
        )
    return "\n".join(lines)


def make_blind_decide_fn(
    llm,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ohlcv_loader: Optional[Callable[[str, str, str], pd.DataFrame]] = None,
) -> Callable[[str, str], str]:
    """Build a (ticker, date) -> rating decision source for BacktestEngine.

    OHLCV is fetched once per ticker for the full needed range and sliced per
    decision date; the LLM sees only the anonymized view, never the ticker.
    """
    cache: dict = {}

    def _default_loader(ticker: str, start: str, end: str) -> pd.DataFrame:
        import yfinance as yf

        hist = yf.Ticker(ticker).history(start=start, end=end)
        if hist.empty:
            raise ValueError(f"No price data for {ticker}")
        return hist

    loader = ohlcv_loader or _default_loader

    def decide(ticker: str, date: str) -> str:
        if ticker not in cache:
            start = (
                datetime.strptime(date, "%Y-%m-%d")
                - timedelta(days=lookback_days + 60)
            ).strftime("%Y-%m-%d")
            far_end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            cache[ticker] = loader(ticker, start, far_end)
        view = prepare_blind_view(cache[ticker], date, lookback_days)
        response = llm.invoke(
            [("system", BLIND_SYSTEM_PROMPT), ("human", view)]
        ).content
        rating = parse_rating(response)
        if rating is None:
            raise ValueError(f"Blind analyst returned no parseable rating: {response[:200]!r}")
        return rating

    return decide

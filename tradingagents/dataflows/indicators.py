"""Technical indicators via the `ta` library (pandas-compatible).

Exposes the same indicator names previously served by stockstats so
market_analyst.py is minimally changed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from .ccxt_market_data import get_ohlcv
from .symbols import Instrument, parse_symbol

logger = logging.getLogger(__name__)

_SUPPORTED = {
    "rsi", "macd", "macds", "macdh",
    "close_50_sma", "close_200_sma", "close_10_ema",
    "boll", "boll_ub", "boll_lb", "atr", "vwma",
}


def _compute(df: pd.DataFrame, indicator: str) -> pd.Series:
    """Compute a single indicator on an OHLCV DataFrame."""
    try:
        import ta
    except ImportError:
        raise ImportError("Install the 'ta' package: pip install ta")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    ind = indicator.lower().strip()

    if ind == "rsi":
        return ta.momentum.RSIIndicator(close=close, window=14).rsi()

    if ind == "macd":
        return ta.trend.MACD(close=close).macd()

    if ind == "macds":
        return ta.trend.MACD(close=close).macd_signal()

    if ind == "macdh":
        return ta.trend.MACD(close=close).macd_diff()

    if ind == "close_50_sma":
        return ta.trend.SMAIndicator(close=close, window=50).sma_indicator()

    if ind == "close_200_sma":
        return ta.trend.SMAIndicator(close=close, window=200).sma_indicator()

    if ind == "close_10_ema":
        return ta.trend.EMAIndicator(close=close, window=10).ema_indicator()

    if ind == "boll":
        return ta.volatility.BollingerBands(close=close, window=20).bollinger_mavg()

    if ind == "boll_ub":
        return ta.volatility.BollingerBands(close=close, window=20).bollinger_hband()

    if ind == "boll_lb":
        return ta.volatility.BollingerBands(close=close, window=20).bollinger_lband()

    if ind == "atr":
        return ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()

    if ind == "vwma":
        if volume.sum() == 0:
            return pd.Series([None] * len(close), index=close.index)
        wsum = (close * volume).rolling(window=20).sum()
        vsum = volume.rolling(window=20).sum()
        return wsum / vsum

    raise ValueError(
        f"Unknown indicator: {indicator!r}. Supported: {sorted(_SUPPORTED)}"
    )


def get_indicator_series(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 60,
) -> str:
    """Return a formatted table of the indicator for the given symbol and date range."""
    try:
        instrument = parse_symbol(symbol)
    except ValueError as e:
        return str(e)

    until = datetime.strptime(curr_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    since = until - timedelta(days=look_back_days + 30)

    df = get_ohlcv(instrument, "1d", since, until)
    if df.empty:
        return f"No OHLCV data available for {symbol}"

    df = df.copy()
    df = df.set_index("timestamp") if "timestamp" in df.columns else df

    ind = indicator.lower().strip()
    if ind not in _SUPPORTED:
        return f"Unknown indicator: {indicator!r}. Supported: {sorted(_SUPPORTED)}"

    try:
        series = _compute(df, ind)
    except Exception as e:
        return f"Error computing {indicator}: {e}"

    df[indicator] = series
    until_dt = pd.Timestamp(curr_date, tz="UTC")
    since_dt = until_dt - pd.Timedelta(days=look_back_days)
    mask = (df.index >= since_dt) & (df.index <= until_dt)
    result = df.loc[mask, [indicator, "close"]].dropna().tail(look_back_days)

    if result.empty:
        return f"No {indicator} data in range for {symbol}"

    return result.to_string()

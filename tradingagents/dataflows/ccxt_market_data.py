"""CCXT-based OHLCV market data with disk caching."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ccxt
import pandas as pd

from .config import get_config
from .symbols import Instrument
from .utils import safe_ticker_component

logger = logging.getLogger(__name__)

_TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def _cache_path(instrument: Instrument, timeframe: str, since: datetime, until: datetime) -> Path:
    config = get_config()
    cache_dir = Path(config["data_cache_dir"]) / "ccxt"
    venue = instrument.venue or "binance"
    safe_base = safe_ticker_component(instrument.base)
    safe_quote = safe_ticker_component(instrument.quote)
    pair_dir = cache_dir / venue / f"{safe_base}_{safe_quote}"
    pair_dir.mkdir(parents=True, exist_ok=True)
    since_s = since.strftime("%Y%m%d")
    until_s = until.strftime("%Y%m%d")
    return pair_dir / f"{timeframe}_{since_s}_{until_s}.parquet"


def _fetch_ohlcv_from_exchange(
    instrument: Instrument, timeframe: str, since_ms: int, until_ms: int
) -> pd.DataFrame:
    venue = instrument.venue or "binance"
    exchange_cls = getattr(ccxt, venue, None)
    if exchange_cls is None:
        raise ValueError(f"Unknown ccxt exchange: {venue!r}")

    exchange = exchange_cls({"enableRateLimit": True})
    symbol = f"{instrument.base}/{instrument.quote}"

    all_candles = []
    cursor = since_ms
    tf_ms = _TIMEFRAME_MS.get(timeframe, 86_400_000)

    for attempt in range(6):
        try:
            while cursor < until_ms:
                candles = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=500)
                if not candles:
                    break
                all_candles.extend(candles)
                cursor = candles[-1][0] + tf_ms
                if cursor >= until_ms:
                    break
            break
        except ccxt.RateLimitExceeded:
            wait = 2 ** attempt
            logger.warning("Rate limited by %s, retrying in %ds", venue, wait)
            time.sleep(wait)
        except ccxt.NetworkError as e:
            if attempt < 5:
                time.sleep(2 ** attempt)
            else:
                raise

    if not all_candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    until_dt = pd.Timestamp(until_ms, unit="ms", tz="UTC")
    df = df[df["timestamp"] <= until_dt]
    return df


def get_ohlcv(
    instrument: Instrument,
    timeframe: str,
    since: datetime,
    until: datetime,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return OHLCV DataFrame for the instrument and date range.

    Results are cached to disk as parquet. Pass ``force_refresh=True`` to
    bypass the cache.
    """
    cache_file = _cache_path(instrument, timeframe, since, until)

    if not force_refresh and cache_file.exists():
        try:
            df = pd.read_parquet(cache_file)
            logger.debug("Cache hit: %s", cache_file)
            return df
        except Exception as e:
            logger.warning("Cache read failed (%s), re-fetching", e)

    since = since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since
    until = until.replace(tzinfo=timezone.utc) if until.tzinfo is None else until
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(until.timestamp() * 1000)

    df = _fetch_ohlcv_from_exchange(instrument, timeframe, since_ms, until_ms)

    try:
        df.to_parquet(cache_file, index=False)
    except Exception as e:
        logger.warning("Cache write failed: %s", e)

    return df

"""Coinglass derivatives data: funding rates, OI, long/short ratio, liquidations.

Requires COINGLASS_API_KEY env var. Free tier: ~30 req/min.
Results are cached in-memory with a 5-minute TTL.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

from .symbols import Instrument

logger = logging.getLogger(__name__)

_BASE_URL = "https://open-api.coinglass.com/public/v2"
_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 300  # 5 minutes


def _api_key() -> Optional[str]:
    return os.environ.get("COINGLASS_API_KEY")


def _get(endpoint: str, params: dict = None) -> Optional[dict]:
    key = _api_key()
    if not key:
        logger.warning("COINGLASS_API_KEY not set")
        return None

    cache_key = f"{endpoint}:{sorted((params or {}).items())}"
    now = time.time()
    if cache_key in _CACHE:
        ts, cached = _CACHE[cache_key]
        if now - ts < _TTL:
            return cached

    try:
        resp = requests.get(
            f"{_BASE_URL}{endpoint}",
            headers={"coinglassSecret": key},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        logger.warning("Coinglass HTTP %s for %s: %s", e.response.status_code, endpoint, e)
        return None
    except Exception as e:
        logger.warning("Coinglass request failed: %s", e)
        return None

    _CACHE[cache_key] = (now, data)
    return data


def get_funding_rate(instrument: Instrument) -> dict:
    """Return current funding rate and 8h history for a perpetual pair."""
    key = _api_key()
    if not key:
        return {"error": "COINGLASS_API_KEY not configured"}

    symbol = instrument.base.upper()
    data = _get("/funding", {"symbol": symbol})
    if not data:
        return {"error": "Coinglass unavailable or API key missing"}

    items = data.get("data", [])
    if not items:
        return {"error": f"No funding rate data for {symbol}"}

    current = items[0] if items else {}
    return {
        "symbol": symbol,
        "current_rate": current.get("fundingRate"),
        "current_rate_annualised_pct": (
            float(current.get("fundingRate", 0)) * 3 * 365 * 100
            if current.get("fundingRate") is not None else None
        ),
        "next_funding_time": current.get("nextFundingTime"),
        "exchange": current.get("exchangeName"),
    }


def get_open_interest(instrument: Instrument) -> dict:
    """Return total OI, 24h change, and per-exchange breakdown."""
    key = _api_key()
    if not key:
        return {"error": "COINGLASS_API_KEY not configured"}

    symbol = instrument.base.upper()
    data = _get("/open_interest", {"symbol": symbol})
    if not data:
        return {"error": "Coinglass unavailable"}

    items = data.get("data", [])
    total_oi = sum(float(x.get("openInterest", 0)) for x in items if x.get("openInterest"))
    total_oi_usd = sum(float(x.get("openInterestAmount", 0)) for x in items if x.get("openInterestAmount"))

    return {
        "symbol": symbol,
        "total_oi_contracts": total_oi,
        "total_oi_usd": total_oi_usd,
        "exchanges": [
            {
                "exchange": x.get("exchangeName"),
                "oi": x.get("openInterest"),
                "oi_usd": x.get("openInterestAmount"),
            }
            for x in items[:5]
        ],
    }


def get_long_short_ratio(instrument: Instrument) -> dict:
    """Return long/short account ratio for the pair."""
    key = _api_key()
    if not key:
        return {"error": "COINGLASS_API_KEY not configured"}

    symbol = instrument.base.upper()
    data = _get("/long_short", {"symbol": symbol, "time_type": "h4", "limit": 1})
    if not data:
        return {"error": "Coinglass unavailable"}

    items = data.get("data", {})
    if isinstance(items, list) and items:
        item = items[0]
    elif isinstance(items, dict):
        item = items
    else:
        return {"error": f"No long/short data for {symbol}"}

    return {
        "symbol": symbol,
        "long_pct": item.get("longRatio") or item.get("longPercent"),
        "short_pct": item.get("shortRatio") or item.get("shortPercent"),
        "long_short_ratio": item.get("longShortRatio"),
    }


def get_liquidations(instrument: Instrument, window: str = "24h") -> dict:
    """Return total long and short liquidations over the specified window."""
    key = _api_key()
    if not key:
        return {"error": "COINGLASS_API_KEY not configured"}

    symbol = instrument.base.upper()
    data = _get("/liquidation_info", {"symbol": symbol})
    if not data:
        return {"error": "Coinglass unavailable"}

    d = data.get("data", {})
    return {
        "symbol": symbol,
        "window": window,
        "long_liquidations_usd": d.get("buyLiquidationAmount24h"),
        "short_liquidations_usd": d.get("sellLiquidationAmount24h"),
        "total_liquidations_usd": d.get("liquidationAmount24h"),
    }

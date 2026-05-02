"""CoinGecko data: market summary and tokenomics. Free tier, no key required."""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"
_HEADERS = {"accept": "application/json"}


def _get_api_key() -> Optional[str]:
    return os.environ.get("COINGECKO_API_KEY")


def _headers() -> dict:
    h = dict(_HEADERS)
    key = _get_api_key()
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def _get(endpoint: str, params: dict = None) -> Optional[dict]:
    url = f"{_BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        logger.warning("CoinGecko HTTP error %s: %s", e.response.status_code, e)
    except Exception as e:
        logger.warning("CoinGecko request failed: %s", e)
    return None


_COIN_ID_CACHE: dict[str, str] = {}


def _resolve_coin_id(base: str) -> Optional[str]:
    base_lower = base.lower()
    if base_lower in _COIN_ID_CACHE:
        return _COIN_ID_CACHE[base_lower]
    data = _get("/search", {"query": base})
    if data and data.get("coins"):
        for coin in data["coins"]:
            if coin.get("symbol", "").lower() == base_lower:
                _COIN_ID_CACHE[base_lower] = coin["id"]
                return coin["id"]
    return None


def get_market_summary(base: str) -> dict:
    """Return market cap, 24h vol, dominance, ATH/ATL, supply for a crypto asset."""
    coin_id = _resolve_coin_id(base)
    if not coin_id:
        return {"error": f"Could not resolve CoinGecko ID for {base!r}"}

    data = _get(f"/coins/{coin_id}", {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
    })
    if not data:
        return {"error": "CoinGecko unavailable"}

    md = data.get("market_data", {})
    return {
        "name": data.get("name"),
        "symbol": data.get("symbol", "").upper(),
        "market_cap_usd": md.get("market_cap", {}).get("usd"),
        "volume_24h_usd": md.get("total_volume", {}).get("usd"),
        "current_price_usd": md.get("current_price", {}).get("usd"),
        "price_change_24h_pct": md.get("price_change_percentage_24h"),
        "price_change_7d_pct": md.get("price_change_percentage_7d"),
        "ath_usd": md.get("ath", {}).get("usd"),
        "ath_change_pct": md.get("ath_change_percentage", {}).get("usd"),
        "atl_usd": md.get("atl", {}).get("usd"),
        "circulating_supply": md.get("circulating_supply"),
        "total_supply": md.get("total_supply"),
        "max_supply": md.get("max_supply"),
        "fdv_usd": md.get("fully_diluted_valuation", {}).get("usd"),
        "market_cap_rank": data.get("market_cap_rank"),
    }


def get_tokenomics(base: str) -> dict:
    """Return token supply dynamics and valuation metrics."""
    coin_id = _resolve_coin_id(base)
    if not coin_id:
        return {"error": f"Could not resolve CoinGecko ID for {base!r}"}

    data = _get(f"/coins/{coin_id}", {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
    })
    if not data:
        return {"error": "CoinGecko unavailable"}

    md = data.get("market_data", {})
    return {
        "symbol": data.get("symbol", "").upper(),
        "circulating_supply": md.get("circulating_supply"),
        "total_supply": md.get("total_supply"),
        "max_supply": md.get("max_supply"),
        "fdv_usd": md.get("fully_diluted_valuation", {}).get("usd"),
        "market_cap_usd": md.get("market_cap", {}).get("usd"),
        "ath_usd": md.get("ath", {}).get("usd"),
        "ath_change_pct": md.get("ath_change_percentage", {}).get("usd"),
        "atl_usd": md.get("atl", {}).get("usd"),
        "price_change_1y_pct": md.get("price_change_percentage_1y"),
    }

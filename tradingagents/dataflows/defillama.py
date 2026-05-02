"""DeFiLlama TVL and protocol revenue data. Free, no auth required."""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.llama.fi"

# Mapping of token symbol → DeFiLlama protocol slug
_SLUG_MAP: dict[str, str] = {
    "UNI": "uniswap",
    "AAVE": "aave",
    "LDO": "lido",
    "MKR": "makerdao",
    "CRV": "curve",
    "COMP": "compound",
    "SNX": "synthetix",
    "BAL": "balancer",
    "SUSHI": "sushiswap",
    "YFI": "yearn-finance",
    "1INCH": "1inch",
    "GMX": "gmx",
    "ARB": "arbitrum",
    "OP": "optimism",
    "JUP": "jupiter",
    "ORCA": "orca",
    "RAY": "raydium",
}


def _resolve_slug(base: str) -> Optional[str]:
    return _SLUG_MAP.get(base.upper())


def get_protocol_tvl(base: str) -> Optional[dict]:
    """Return TVL data for a DeFi protocol. Returns None if unmapped."""
    slug = _resolve_slug(base)
    if not slug:
        return None
    try:
        resp = requests.get(f"{_BASE_URL}/protocol/{slug}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("DeFiLlama TVL error for %s: %s", base, e)
        return {"error": str(e)}

    tvl_data = data.get("currentChainTvls", {})
    total_tvl = sum(tvl_data.values()) if tvl_data else data.get("tvl")

    return {
        "protocol": data.get("name"),
        "slug": slug,
        "total_tvl_usd": total_tvl,
        "chains": list(tvl_data.keys()) if tvl_data else [],
        "category": data.get("category"),
    }


def get_protocol_revenue(base: str) -> Optional[dict]:
    """Return 24h/7d/30d revenue for a DeFi protocol. Returns None if unavailable."""
    slug = _resolve_slug(base)
    if not slug:
        return None
    try:
        resp = requests.get(f"{_BASE_URL}/summary/fees/{slug}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("DeFiLlama revenue error for %s: %s", base, e)
        return None

    return {
        "protocol": data.get("name"),
        "total24h_fees_usd": data.get("total24h"),
        "total7d_fees_usd": data.get("total7d"),
        "total30d_fees_usd": data.get("total30d"),
        "revenue_24h_usd": data.get("totalRevenue24h"),
        "revenue_7d_usd": data.get("totalRevenue7d"),
    }

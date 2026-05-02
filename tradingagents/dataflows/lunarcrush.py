"""LunarCrush social sentiment data. Requires LUNARCRUSH_API_KEY env var."""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://lunarcrush.com/api4/public"


def _api_key() -> Optional[str]:
    return os.environ.get("LUNARCRUSH_API_KEY")


def get_social_metrics(base: str) -> dict:
    """Return galaxy_score, alt_rank, social_volume, sentiment for a crypto asset."""
    key = _api_key()
    if not key:
        logger.warning("LUNARCRUSH_API_KEY not set; returning empty social metrics")
        return {"error": "LUNARCRUSH_API_KEY not configured"}

    try:
        resp = requests.get(
            f"{_BASE_URL}/coins/{base.lower()}/v1",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except requests.HTTPError as e:
        logger.warning("LunarCrush HTTP error %s", e)
        return {"error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        logger.warning("LunarCrush request failed: %s", e)
        return {"error": str(e)}

    return {
        "symbol": data.get("symbol", "").upper(),
        "galaxy_score": data.get("galaxy_score"),
        "alt_rank": data.get("alt_rank"),
        "social_volume_24h": data.get("social_volume_24h"),
        "social_dominance": data.get("social_dominance"),
        "sentiment": data.get("sentiment"),
        "market_cap_rank": data.get("market_cap_rank"),
    }

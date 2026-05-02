"""CryptoPanic news aggregator. Requires CRYPTOPANIC_TOKEN env var."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://cryptopanic.com/api/v1"


def _token() -> Optional[str]:
    return os.environ.get("CRYPTOPANIC_TOKEN")


def get_news(
    base: str,
    start_date: str,
    end_date: str,
    limit: int = 50,
) -> str:
    """Return news articles for a crypto asset. Falls back gracefully when token missing."""
    token = _token()
    if not token:
        logger.warning("CRYPTOPANIC_TOKEN not set; returning empty news")
        return f"News data unavailable for {base}: CRYPTOPANIC_TOKEN not configured."

    params = {
        "auth_token": token,
        "currencies": base.upper(),
        "public": "true",
        "kind": "news",
    }
    try:
        resp = requests.get(f"{_BASE_URL}/posts/", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        logger.warning("CryptoPanic HTTP error %s", e)
        return f"News temporarily unavailable for {base} (HTTP {e.response.status_code})."
    except Exception as e:
        logger.warning("CryptoPanic request failed: %s", e)
        return f"News temporarily unavailable for {base}."

    results = data.get("results", [])[:limit]
    if not results:
        return f"No news found for {base} in the specified period."

    lines = [f"### News for {base.upper()} ({start_date} – {end_date})\n"]
    for item in results:
        pub = item.get("published_at", "")[:10]
        title = item.get("title", "No title")
        source = item.get("source", {}).get("title", "Unknown")
        url = item.get("url", "")
        votes = item.get("votes", {})
        sentiment = "bullish" if votes.get("positive", 0) > votes.get("negative", 0) else (
            "bearish" if votes.get("negative", 0) > votes.get("positive", 0) else "neutral"
        )
        lines.append(f"- [{pub}] **{title}** — {source} ({sentiment})\n  {url}")

    return "\n".join(lines)


def get_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 20,
) -> str:
    """Return broad crypto market news (no currency filter)."""
    token = _token()
    if not token:
        logger.warning("CRYPTOPANIC_TOKEN not set; returning empty global news")
        return "Global crypto news unavailable: CRYPTOPANIC_TOKEN not configured."

    params = {
        "auth_token": token,
        "public": "true",
        "kind": "news",
    }
    try:
        resp = requests.get(f"{_BASE_URL}/posts/", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("CryptoPanic global news failed: %s", e)
        return "Global crypto news temporarily unavailable."

    results = data.get("results", [])[:limit]
    if not results:
        return "No global crypto news found."

    lines = [f"### Global Crypto News (as of {curr_date})\n"]
    for item in results:
        pub = item.get("published_at", "")[:10]
        title = item.get("title", "No title")
        source = item.get("source", {}).get("title", "Unknown")
        lines.append(f"- [{pub}] **{title}** — {source}")

    return "\n".join(lines)

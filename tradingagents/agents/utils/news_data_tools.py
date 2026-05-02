from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.cryptopanic import (
    get_news as _get_news,
    get_global_news as _get_global_news,
)


@tool
def get_news(
    ticker: Annotated[str, "Crypto asset base symbol or pair, e.g. BTC or BTC/USDT"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news articles for a crypto asset.
    Uses CryptoPanic (requires CRYPTOPANIC_TOKEN env var).
    Falls back gracefully if token is not configured.
    Args:
        ticker: Crypto asset symbol (e.g. 'BTC', 'ETH', 'BTC/USDT')
        start_date: Start date yyyy-mm-dd
        end_date: End date yyyy-mm-dd
    Returns:
        str: Formatted news articles with sentiment indicators.
    """
    base = ticker.split("/")[0].split(":")[- 1].upper() if "/" in ticker or ":" in ticker else ticker.upper()
    return _get_news(base, start_date, end_date)


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 20,
) -> str:
    """
    Retrieve broad crypto market news (not filtered by specific asset).
    Uses CryptoPanic (requires CRYPTOPANIC_TOKEN env var).
    Args:
        curr_date: Current date yyyy-mm-dd
        look_back_days: Number of days to look back (default 7)
        limit: Maximum number of articles (default 20)
    Returns:
        str: Formatted global crypto news.
    """
    return _get_global_news(curr_date, look_back_days, limit)

"""Vendor routing layer for all data tools.

Maps method names to their provider implementations. Add new providers by
extending VENDOR_METHODS and TOOLS_CATEGORIES.
"""

from typing import Annotated

from .ccxt_market_data import get_ohlcv
from .cryptopanic import get_news as get_cryptopanic_news, get_global_news as get_cryptopanic_global_news
from .config import get_config

TOOLS_CATEGORIES = {
    "market_data": {
        "description": "OHLCV crypto price data",
        "tools": ["get_market_data"],
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": ["get_indicators"],
    },
    "news_data": {
        "description": "Crypto news",
        "tools": ["get_news", "get_global_news"],
    },
    "social_data": {
        "description": "Social sentiment",
        "tools": ["get_social_metrics"],
    },
    "onchain_data": {
        "description": "On-chain data",
        "tools": ["get_funding_rate", "get_open_interest", "get_long_short_ratio", "get_liquidations"],
    },
    "derivatives_data": {
        "description": "Derivatives market data",
        "tools": ["get_funding_rate", "get_open_interest", "get_long_short_ratio", "get_liquidations"],
    },
    "tokenomics_data": {
        "description": "Token supply and protocol metrics",
        "tools": ["get_tokenomics", "get_protocol_metrics"],
    },
}

VENDOR_LIST = ["ccxt", "cryptopanic", "lunarcrush", "coinglass", "coingecko", "defillama"]


def _get_market_data_ccxt(symbol, start_date, end_date):
    from datetime import datetime, timezone
    from .symbols import parse_symbol
    instrument = parse_symbol(symbol)
    since = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    until = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    df = get_ohlcv(instrument, "1d", since, until)
    return df.to_string(index=False) if not df.empty else f"No data for {symbol}"


def _get_indicators_ta(symbol, indicator, curr_date, look_back_days=30):
    from .indicators import get_indicator_series
    return get_indicator_series(symbol, indicator, curr_date, look_back_days)


VENDOR_METHODS = {
    "get_market_data": {
        "ccxt": _get_market_data_ccxt,
    },
    "get_indicators": {
        "pandas_ta": _get_indicators_ta,
    },
    "get_news": {
        "cryptopanic": get_cryptopanic_news,
    },
    "get_global_news": {
        "cryptopanic": get_cryptopanic_global_news,
    },
}


def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None) -> str:
    config = get_config()
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    return config.get("data_vendors", {}).get(category, "default")


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to the configured vendor implementation."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",")]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for v in all_available:
        if v not in fallback_vendors:
            fallback_vendors.append(v)

    last_err = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue
        impl = VENDOR_METHODS[method][vendor]
        try:
            return impl(*args, **kwargs)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(
        f"No available vendor for '{method}'"
        + (f": {last_err}" if last_err else "")
    )

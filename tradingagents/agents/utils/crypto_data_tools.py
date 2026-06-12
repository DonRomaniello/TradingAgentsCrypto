"""Crypto-native data tools: derivatives positioning and crowd sentiment.

These are the signals that actually drive crypto price action and have no
equity analogue. Each tool guards against non-crypto tickers so an LLM
mis-call returns an explanation instead of garbage.
"""

from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.utils import is_crypto_pair
from tradingagents.dataflows import crypto_utils


def _not_crypto(ticker: str) -> str:
    return (
        f"{ticker} is not a crypto pair; this tool only applies to crypto "
        "assets (e.g. BTC-USD). Use the equity data tools instead."
    )


@tool
def get_funding_rates(
    ticker: Annotated[str, "Crypto pair, e.g. BTC-USD"],
    curr_date: Annotated[str, "Current date you are trading at, yyyy-mm-dd"],
    look_back_days: Annotated[int, "Days of funding history to summarize"] = 7,
) -> str:
    """
    Retrieve perpetual-futures funding rates for a crypto pair (Binance).
    Persistent positive funding = crowded longs; negative = crowded shorts.
    Historical and backtest-safe.
    """
    if not is_crypto_pair(ticker):
        return _not_crypto(ticker)
    return crypto_utils.get_funding_rates(ticker, curr_date, look_back_days)


@tool
def get_open_interest(
    ticker: Annotated[str, "Crypto pair, e.g. BTC-USD"],
    curr_date: Annotated[str, "Current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve perpetual-futures open interest history for a crypto pair
    (Binance, ~30 days of daily data). Rising OI = leverage building;
    falling OI = deleveraging.
    """
    if not is_crypto_pair(ticker):
        return _not_crypto(ticker)
    return crypto_utils.get_open_interest(ticker, curr_date)


@tool
def get_fear_greed_index(
    curr_date: Annotated[str, "Current date you are trading at, yyyy-mm-dd"],
    look_back_days: Annotated[int, "Days of index history to summarize"] = 14,
) -> str:
    """
    Retrieve the crypto Fear & Greed index (market-wide crowd sentiment,
    0=extreme fear to 100=extreme greed). Full daily history, backtest-safe.
    """
    return crypto_utils.get_fear_greed_index(curr_date, look_back_days)

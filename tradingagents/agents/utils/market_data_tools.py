from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime, timedelta, timezone

from tradingagents.dataflows.ccxt_market_data import get_ohlcv
from tradingagents.dataflows.indicators import get_indicator_series
from tradingagents.dataflows.symbols import parse_symbol


@tool
def get_market_data(
    symbol: Annotated[str, "Crypto pair symbol, e.g. BTC/USDT or binance:ETH/USDT"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve OHLCV market data for a crypto pair from the configured exchange.
    Args:
        symbol: Crypto pair symbol, e.g. 'BTC/USDT', 'binance:ETH/USDT'
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format
    Returns:
        str: Formatted DataFrame with open, high, low, close, volume columns.
    """
    try:
        instrument = parse_symbol(symbol)
    except ValueError as e:
        return str(e)

    try:
        since = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        until = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as e:
        return f"Invalid date format: {e}"

    df = get_ohlcv(instrument, "1d", since, until)
    if df.empty:
        return f"No data found for {symbol} between {start_date} and {end_date}"
    return df.to_string(index=False)


@tool
def get_indicators(
    symbol: Annotated[str, "Crypto pair symbol, e.g. BTC/USDT"],
    indicator: Annotated[str, "Technical indicator name(s), e.g. 'rsi', 'macd'. Comma-separated for multiple."],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "How many days to look back"] = 30,
) -> str:
    """
    Retrieve technical indicator(s) for a crypto pair.
    Supported indicators: rsi, macd, macds, macdh, close_50_sma, close_200_sma,
    close_10_ema, boll, boll_ub, boll_lb, atr, vwma.
    Args:
        symbol: Crypto pair symbol
        indicator: Single indicator name or comma-separated list
        curr_date: Current trading date YYYY-mm-dd
        look_back_days: Days to look back (default 30)
    Returns:
        str: Formatted table of indicator values.
    """
    indicators = [i.strip().lower() for i in indicator.split(",") if i.strip()]
    results = []
    for ind in indicators:
        try:
            results.append(get_indicator_series(symbol, ind, curr_date, look_back_days))
        except Exception as e:
            results.append(f"Error for {ind}: {e}")
    return "\n\n".join(results)

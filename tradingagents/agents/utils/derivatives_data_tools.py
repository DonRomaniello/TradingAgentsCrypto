from langchain_core.tools import tool
from typing import Annotated


def _fmt(data: dict, label: str) -> str:
    if not data or "error" in data:
        return f"{label} unavailable: {data.get('error', 'no data') if data else 'no data'}"
    lines = [f"### {label}"]
    for k, v in data.items():
        if v is not None:
            lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)


@tool
def get_funding_rate(
    symbol: Annotated[str, "Crypto pair symbol, e.g. BTC/USDT"],
) -> str:
    """
    Retrieve current funding rate and 8h history for a perpetual futures pair.
    Positive funding = longs pay shorts (crowded long). Negative = shorts pay longs.
    Requires COINGLASS_API_KEY.
    Args:
        symbol: Crypto pair symbol, e.g. 'BTC/USDT'
    Returns:
        str: Formatted funding rate report.
    """
    from tradingagents.dataflows.coinglass import get_funding_rate as _get
    from tradingagents.dataflows.symbols import parse_symbol
    try:
        instrument = parse_symbol(symbol)
    except ValueError as e:
        return str(e)
    return _fmt(_get(instrument), f"Funding Rate: {symbol}")


@tool
def get_open_interest(
    symbol: Annotated[str, "Crypto pair symbol, e.g. BTC/USDT"],
) -> str:
    """
    Retrieve open interest data for a perp pair: total OI, 24h change, by exchange.
    OI rising with price = healthy trend; OI rising with price falling = shorts piling in.
    Requires COINGLASS_API_KEY.
    Args:
        symbol: Crypto pair symbol
    Returns:
        str: Formatted open interest report.
    """
    from tradingagents.dataflows.coinglass import get_open_interest as _get
    from tradingagents.dataflows.symbols import parse_symbol
    try:
        instrument = parse_symbol(symbol)
    except ValueError as e:
        return str(e)
    return _fmt(_get(instrument), f"Open Interest: {symbol}")


@tool
def get_long_short_ratio(
    symbol: Annotated[str, "Crypto pair symbol, e.g. BTC/USDT"],
) -> str:
    """
    Retrieve long/short ratio for a perp futures pair.
    Ratio > 1 = more longs; < 1 = more shorts.
    Requires COINGLASS_API_KEY.
    Args:
        symbol: Crypto pair symbol
    Returns:
        str: Formatted long/short ratio report.
    """
    from tradingagents.dataflows.coinglass import get_long_short_ratio as _get
    from tradingagents.dataflows.symbols import parse_symbol
    try:
        instrument = parse_symbol(symbol)
    except ValueError as e:
        return str(e)
    return _fmt(_get(instrument), f"Long/Short Ratio: {symbol}")


@tool
def get_liquidations(
    symbol: Annotated[str, "Crypto pair symbol, e.g. BTC/USDT"],
    window: Annotated[str, "Time window, e.g. '24h', '12h'"] = "24h",
) -> str:
    """
    Retrieve liquidation data for a perp pair: total long and short liquidations.
    Large liquidation spikes often precede or accompany price reversals.
    Requires COINGLASS_API_KEY.
    Args:
        symbol: Crypto pair symbol
        window: Time window (default '24h')
    Returns:
        str: Formatted liquidations report.
    """
    from tradingagents.dataflows.coinglass import get_liquidations as _get
    from tradingagents.dataflows.symbols import parse_symbol
    try:
        instrument = parse_symbol(symbol)
    except ValueError as e:
        return str(e)
    return _fmt(_get(instrument, window), f"Liquidations ({window}): {symbol}")

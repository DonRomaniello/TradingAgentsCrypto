from langchain_core.tools import tool
from typing import Annotated


@tool
def get_tokenomics(
    base: Annotated[str, "Crypto asset base symbol, e.g. BTC, ETH, UNI"],
) -> str:
    """
    Retrieve token supply dynamics and valuation metrics for a crypto asset.
    Includes circulating supply, total supply, max supply, FDV vs market cap, ATH.
    Args:
        base: Crypto asset base symbol
    Returns:
        str: Formatted tokenomics report.
    """
    from tradingagents.dataflows.coingecko import get_tokenomics as _get
    data = _get(base)
    if not data or "error" in data:
        return f"Tokenomics unavailable for {base}: {data.get('error', 'no data') if data else 'no data'}"
    lines = [f"### Tokenomics for {base.upper()}"]
    for k, v in data.items():
        if v is not None:
            lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)


@tool
def get_protocol_metrics(
    base: Annotated[str, "DeFi protocol base token symbol, e.g. UNI, AAVE, LDO"],
) -> str:
    """
    Retrieve DeFi protocol metrics: TVL, revenue, fees from DeFiLlama.
    Only relevant for DeFi protocol tokens; returns None for non-DeFi assets.
    Args:
        base: Protocol token symbol
    Returns:
        str: Formatted protocol metrics report.
    """
    from tradingagents.dataflows.defillama import get_protocol_tvl, get_protocol_revenue
    tvl = get_protocol_tvl(base)
    rev = get_protocol_revenue(base)
    if tvl is None and rev is None:
        return f"No DeFiLlama protocol data found for {base}. This may not be a tracked DeFi protocol."
    lines = [f"### Protocol Metrics for {base.upper()} (DeFiLlama)"]
    if tvl:
        for k, v in tvl.items():
            lines.append(f"- **{k}**: {v}")
    if rev:
        lines.append("#### Revenue")
        for k, v in rev.items():
            lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)

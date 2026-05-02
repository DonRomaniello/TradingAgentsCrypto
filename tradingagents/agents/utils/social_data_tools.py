from langchain_core.tools import tool
from typing import Annotated


@tool
def get_social_metrics(
    base: Annotated[str, "Crypto asset base symbol, e.g. BTC, ETH"],
) -> str:
    """
    Retrieve social sentiment metrics for a crypto asset (galaxy score, alt rank,
    social volume, sentiment). Requires LUNARCRUSH_API_KEY.
    Args:
        base: Crypto asset base symbol, e.g. 'BTC', 'ETH'
    Returns:
        str: Formatted social metrics report.
    """
    from tradingagents.dataflows.lunarcrush import get_social_metrics as _get
    data = _get(base)
    if not data or "error" in data:
        return f"Social metrics unavailable for {base}: {data.get('error', 'unknown error') if data else 'no data'}"
    lines = [f"### Social Metrics for {base.upper()}"]
    for k, v in data.items():
        lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)

"""Performance metrics for backtest equity curves."""

from __future__ import annotations

import math
from typing import Sequence


def max_drawdown(equity: Sequence[float]) -> float:
    """Largest peak-to-trough decline of an equity curve, as a negative fraction.

    Returns 0.0 for flat or monotonically rising curves.
    """
    peak = float("-inf")
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return worst


def sharpe_ratio(
    daily_returns: Sequence[float], periods_per_year: int = 365
) -> float | None:
    """Annualised Sharpe ratio (risk-free rate assumed 0).

    ``periods_per_year`` should be 365 for 24/7 crypto bars and 252 for
    equity trading days. Returns None when there is no variance to divide by
    (fewer than 2 bars, or a constant series).
    """
    n = len(daily_returns)
    if n < 2:
        return None
    mean = sum(daily_returns) / n
    var = sum((r - mean) ** 2 for r in daily_returns) / (n - 1)
    if var == 0:
        return None
    return (mean / math.sqrt(var)) * math.sqrt(periods_per_year)


def annualised_return(
    total_return: float, n_periods: int, periods_per_year: int = 365
) -> float | None:
    """Geometric annualisation of a total return over ``n_periods`` bars."""
    if n_periods <= 0 or total_return <= -1:
        return None
    return (1 + total_return) ** (periods_per_year / n_periods) - 1

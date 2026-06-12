"""Backtesting harness for TradingAgents.

Runs the full agent pipeline over a sequence of historical dates, maps the
5-tier ratings onto portfolio exposure, simulates the resulting equity curve
against daily closes (with trading costs), and reports performance vs
buy-and-hold.

The engine separates the *decision source* (an injectable callable) from the
*simulation* so the accounting can be tested deterministically and cheaply;
the default decision source wraps ``TradingAgentsGraph.propagate``.
"""

from tradingagents.backtest.engine import BacktestEngine, BacktestResult, EXPOSURE_MAP
from tradingagents.backtest.metrics import max_drawdown, sharpe_ratio

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "EXPOSURE_MAP",
    "max_drawdown",
    "sharpe_ratio",
]

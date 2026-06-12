"""Backtest engine: decision collection, exposure simulation, accounting.

Execution model (deliberately conservative, no look-ahead):

- The pipeline is asked for a rating on each decision date; agents only see
  data up to that date.
- The resulting exposure change executes at the close of the decision date
  (the same close the agents could observe). Returns accrue to the *prior*
  exposure until that close.
- ``Hold`` keeps the previous exposure and trades nothing, so it costs
  nothing. Every other rating maps to a long-only target exposure and pays
  ``cost_bps`` on turnover (exchange fee + slippage).

Decisions are persisted to a JSONL file as they are made, so an interrupted
backtest resumes without re-running (or re-paying for) completed dates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from tradingagents.backtest.metrics import (
    annualised_return,
    max_drawdown,
    sharpe_ratio,
)
from tradingagents.dataflows.utils import is_crypto_pair, safe_ticker_component

logger = logging.getLogger(__name__)

# Long-only exposure targets per rating. None = keep previous exposure.
EXPOSURE_MAP: Dict[str, Optional[float]] = {
    "Buy": 1.0,
    "Overweight": 0.75,
    "Hold": None,
    "Underweight": 0.25,
    "Sell": 0.0,
}

_BULLISH = {"Buy", "Overweight"}
_BEARISH = {"Underweight", "Sell"}

# Signals that are NOT point-in-time for historical dates. A backtest is only
# as honest as its inputs; these caveats ship with every report.
DATA_INTEGRITY_WARNINGS = [
    "Prices, technical indicators, funding rates, and the Fear & Greed index "
    "are date-bounded and point-in-time honest.",
    "News coverage is NOT point-in-time: yfinance only serves recent articles, "
    "so historical dates run mostly news-blind while live runs are news-rich. "
    "Backtest results understate (or misstate) the value of the news analyst.",
    "Fundamentals snapshots (market cap, supply, company info) reflect the "
    "PRESENT, not the trade date — a known look-ahead for historical runs.",
    "LLM training data may include knowledge of what happened after the trade "
    "date. Prefer dates after the model's knowledge cutoff for honest results.",
]


def yfinance_price_loader(ticker: str, start: str, end: str) -> pd.Series:
    """Daily closes for [start, end], date-indexed and timezone-naive."""
    import yfinance as yf

    end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
    hist = yf.Ticker(ticker).history(start=start, end=end_dt.strftime("%Y-%m-%d"))
    if hist.empty:
        raise ValueError(f"No price data for {ticker} between {start} and {end}")
    closes = hist["Close"]
    closes.index = closes.index.tz_localize(None).normalize()
    return closes


@dataclass
class BacktestResult:
    ticker: str
    start_date: str
    end_date: str
    decisions: List[dict]
    equity: pd.Series
    metrics: dict
    warnings: List[str] = field(default_factory=list)


class BacktestEngine:
    """Run a decision source over historical dates and account for the results.

    Args:
        ticker: instrument to test (e.g. "BTC-USD").
        start_date / end_date: inclusive yyyy-mm-dd range.
        cadence_days: calendar days between decisions.
        cost_bps: round-trip-side cost per unit of turnover, in basis points
            (10 = 0.10% per full position flip side).
        decide_fn: ``f(ticker, date_str) -> rating`` — the decision source.
            Wrap TradingAgentsGraph for real runs; inject a stub for tests.
        price_loader: ``f(ticker, start, end) -> pd.Series`` of daily closes.
        decisions_path: JSONL file for incremental persistence/resume. None
            disables persistence.
        exposure_map: override the rating -> exposure mapping.
    """

    def __init__(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        cadence_days: int = 7,
        cost_bps: float = 10.0,
        decide_fn: Optional[Callable[[str, str], str]] = None,
        price_loader: Callable[[str, str, str], pd.Series] = yfinance_price_loader,
        decisions_path: Optional[Path] = None,
        exposure_map: Optional[Dict[str, Optional[float]]] = None,
    ):
        if decide_fn is None:
            raise ValueError("decide_fn is required (wrap TradingAgentsGraph or inject a stub)")
        safe_ticker_component(ticker)
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.cadence_days = cadence_days
        self.cost_rate = cost_bps / 10_000.0
        self.decide_fn = decide_fn
        self.price_loader = price_loader
        self.decisions_path = Path(decisions_path) if decisions_path else None
        self.exposure_map = exposure_map or EXPOSURE_MAP

    # --- Decision collection -------------------------------------------------

    def decision_dates(self) -> List[str]:
        dates = []
        d = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")
        while d <= end:
            dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=self.cadence_days)
        return dates

    def _load_saved_decisions(self) -> Dict[str, str]:
        saved: Dict[str, str] = {}
        if self.decisions_path and self.decisions_path.exists():
            for line in self.decisions_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("ticker") == self.ticker:
                    saved[row["date"]] = row["rating"]
        return saved

    def _save_decision(self, date: str, rating: str) -> None:
        if not self.decisions_path:
            return
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.decisions_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ticker": self.ticker, "date": date, "rating": rating}) + "\n")

    def collect_decisions(self) -> Dict[str, str]:
        """Rating per decision date, resuming from persisted decisions."""
        saved = self._load_saved_decisions()
        ratings: Dict[str, str] = {}
        dates = self.decision_dates()
        for i, date in enumerate(dates):
            if date in saved:
                ratings[date] = saved[date]
                continue
            logger.info("Backtest %s: deciding %s (%d/%d)", self.ticker, date, i + 1, len(dates))
            try:
                rating = self.decide_fn(self.ticker, date)
            except Exception as e:
                logger.error("Decision failed for %s on %s: %s — skipping date", self.ticker, date, e)
                continue
            if rating not in self.exposure_map:
                logger.error("Unknown rating %r for %s on %s — skipping date", rating, self.ticker, date)
                continue
            ratings[date] = rating
            self._save_decision(date, rating)
        return ratings

    # --- Simulation ----------------------------------------------------------

    def simulate(self, prices: pd.Series, ratings: Dict[str, str]) -> BacktestResult:
        """Account an exposure path over daily closes given dated ratings."""
        prices = prices.sort_index()
        idx = prices.index

        # Map each decision date to its execution bar: the last bar at or
        # before the decision date (equities may have no bar on a weekend).
        exec_bar: Dict[int, dict] = {}
        for date, rating in sorted(ratings.items()):
            d = pd.Timestamp(date)
            mask = idx <= d
            if not mask.any():
                logger.warning("No price bar at or before %s; dropping decision", date)
                continue
            bar = int(mask.sum() - 1)
            # Later decisions overwrite earlier ones landing on the same bar.
            exec_bar[bar] = {"date": date, "rating": rating}

        exposure = 0.0
        equity = [1.0]
        decisions: List[dict] = []

        def execute(bar: int, eq: float) -> float:
            info = exec_bar[bar]
            target = self.exposure_map[info["rating"]]
            if target is None:  # Hold: keep exposure, no trade, no cost
                target = exposure
            turnover = abs(target - exposure)
            cost = turnover * self.cost_rate
            decisions.append(
                {
                    "date": info["date"],
                    "rating": info["rating"],
                    "exec_date": str(idx[bar].date()),
                    "exec_price": float(prices.iloc[bar]),
                    "exposure": target,
                    "turnover": turnover,
                    "cost": cost,
                }
            )
            return eq * (1 - cost), target

        if 0 in exec_bar:
            eq, exposure = execute(0, equity[0])
            equity[0] = eq

        for i in range(1, len(prices)):
            ret = float(prices.iloc[i] / prices.iloc[i - 1] - 1)
            eq = equity[-1] * (1 + exposure * ret)
            if i in exec_bar:
                eq, exposure = execute(i, eq)
            equity.append(eq)

        equity_series = pd.Series(equity, index=idx)
        metrics = self._compute_metrics(prices, equity_series, decisions)
        return BacktestResult(
            ticker=self.ticker,
            start_date=self.start_date,
            end_date=self.end_date,
            decisions=decisions,
            equity=equity_series,
            metrics=metrics,
            warnings=list(DATA_INTEGRITY_WARNINGS),
        )

    def _compute_metrics(
        self, prices: pd.Series, equity: pd.Series, decisions: List[dict]
    ) -> dict:
        periods = 365 if is_crypto_pair(self.ticker) else 252
        n_bars = len(prices) - 1

        strat_ret = equity.pct_change().dropna()
        # Initial capital is 1.0 by construction; equity.iloc[0] may already
        # include a day-0 trading cost, which must count against the return.
        total = float(equity.iloc[-1] - 1.0)
        bh_total = float(prices.iloc[-1] / prices.iloc[0] - 1)

        # Directional hit rate: forward return from execution to the next
        # decision's execution (or the final bar). Hold has no direction.
        hits = misses = 0
        for j, dec in enumerate(decisions):
            if dec["rating"] not in _BULLISH | _BEARISH:
                dec["forward_return"] = None
                dec["correct"] = None
                continue
            entry_price = dec["exec_price"]
            exit_price = (
                decisions[j + 1]["exec_price"] if j + 1 < len(decisions)
                else float(prices.iloc[-1])
            )
            fwd = exit_price / entry_price - 1
            correct = fwd > 0 if dec["rating"] in _BULLISH else fwd < 0
            dec["forward_return"] = fwd
            dec["correct"] = correct
            hits += int(correct)
            misses += int(not correct)

        directional = hits + misses
        return {
            "n_decisions": len(decisions),
            "n_directional": directional,
            "hit_rate": hits / directional if directional else None,
            "total_return": total,
            "annualised_return": annualised_return(total, n_bars, periods),
            "buy_hold_return": bh_total,
            "excess_vs_buy_hold": total - bh_total,
            "sharpe": sharpe_ratio(strat_ret.tolist(), periods),
            "buy_hold_sharpe": sharpe_ratio(
                prices.pct_change().dropna().tolist(), periods
            ),
            "max_drawdown": max_drawdown(equity.tolist()),
            "buy_hold_max_drawdown": max_drawdown(prices.tolist()),
            "total_costs": sum(d["cost"] for d in decisions),
            "bars": len(prices),
        }

    # --- Orchestration -------------------------------------------------------

    def run(self) -> BacktestResult:
        ratings = self.collect_decisions()
        if not ratings:
            raise ValueError("Backtest produced no usable decisions")
        prices = self.price_loader(self.ticker, self.start_date, self.end_date)
        return self.simulate(prices, ratings)

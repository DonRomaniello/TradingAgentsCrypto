"""Deterministic tests for the backtest engine's accounting.

The decision source is injected, so no LLM or network is involved; prices
are synthetic series with known returns so every metric can be verified by
hand.
"""

import json
from datetime import datetime

import pandas as pd
import pytest

from tradingagents.backtest import BacktestEngine
from tradingagents.backtest.metrics import max_drawdown, sharpe_ratio
from tradingagents.backtest.report import render_markdown, save_report


def _prices(start: str, closes):
    idx = pd.date_range(start=start, periods=len(closes), freq="D")
    return pd.Series(closes, index=idx)


def _engine(ratings_by_date, prices, **kwargs):
    """Engine with an injected decision source and price series."""
    dates = sorted(ratings_by_date)
    return BacktestEngine(
        ticker=kwargs.pop("ticker", "BTC-USD"),
        start_date=dates[0],
        end_date=dates[-1],
        decide_fn=lambda t, d: ratings_by_date[d],
        price_loader=lambda t, s, e: prices,
        **kwargs,
    )


@pytest.mark.unit
class TestMetrics:
    def test_max_drawdown(self):
        assert max_drawdown([1.0, 1.2, 0.9, 1.1]) == pytest.approx(-0.25)
        assert max_drawdown([1.0, 1.1, 1.2]) == 0.0

    def test_sharpe_none_for_constant_series(self):
        assert sharpe_ratio([0.0, 0.0, 0.0]) is None
        assert sharpe_ratio([0.01]) is None

    def test_sharpe_sign_follows_mean(self):
        assert sharpe_ratio([0.01, 0.02, 0.015, 0.01]) > 0
        assert sharpe_ratio([-0.01, -0.02, -0.015, -0.01]) < 0


@pytest.mark.unit
class TestSimulation:
    def test_buy_then_flat_tracks_asset(self):
        # Buy at 100 on day 0 with zero cost: strategy must equal buy & hold.
        prices = _prices("2026-01-01", [100, 110, 121])
        eng = _engine({"2026-01-01": "Buy"}, prices, cost_bps=0.0)
        result = eng.run()
        assert result.metrics["total_return"] == pytest.approx(0.21)
        assert result.metrics["buy_hold_return"] == pytest.approx(0.21)
        assert result.metrics["excess_vs_buy_hold"] == pytest.approx(0.0)

    def test_sell_avoids_losses(self):
        prices = _prices("2026-01-01", [100, 90, 81])
        eng = _engine({"2026-01-01": "Sell"}, prices, cost_bps=0.0)
        result = eng.run()
        # Never long: flat equity while the asset loses 19%.
        assert result.metrics["total_return"] == pytest.approx(0.0)
        assert result.metrics["buy_hold_return"] == pytest.approx(-0.19)

    def test_hold_keeps_previous_exposure_and_costs_nothing(self):
        prices = _prices("2026-01-01", [100, 100, 100, 100, 110])
        eng = _engine(
            {"2026-01-01": "Buy", "2026-01-03": "Hold"}, prices,
            cadence_days=2, cost_bps=0.0,
        )
        result = eng.run()
        # Hold keeps the Buy exposure of 1.0, so the final 10% move is captured.
        assert result.metrics["total_return"] == pytest.approx(0.10)
        hold = [d for d in result.decisions if d["rating"] == "Hold"][0]
        assert hold["exposure"] == 1.0
        assert hold["turnover"] == 0.0
        assert hold["cost"] == 0.0

    def test_partial_exposure_scales_returns(self):
        prices = _prices("2026-01-01", [100, 110])
        eng = _engine({"2026-01-01": "Overweight"}, prices, cost_bps=0.0)
        result = eng.run()
        # 0.75 exposure on a +10% move = +7.5%.
        assert result.metrics["total_return"] == pytest.approx(0.075)

    def test_costs_charged_on_turnover(self):
        prices = _prices("2026-01-01", [100, 100])
        # 100 bps cost, full flip from 0 to 1: equity drops 1% with flat prices.
        eng = _engine({"2026-01-01": "Buy"}, prices, cost_bps=100.0)
        result = eng.run()
        assert result.metrics["total_return"] == pytest.approx(-0.01)
        assert result.metrics["total_costs"] == pytest.approx(0.01)

    def test_no_lookahead_exposure_starts_at_decision(self):
        # Decision on day 2: the +50% move on day 1 must NOT be captured.
        prices = _prices("2026-01-01", [100, 150, 150, 165])
        eng = _engine({"2026-01-03": "Buy"}, prices, cost_bps=0.0)
        result = eng.run()
        assert result.metrics["total_return"] == pytest.approx(0.10)

    def test_decision_on_non_trading_day_executes_at_prior_close(self):
        # Equity-style gap: no bar on 2026-01-03/04 (weekend).
        idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"])
        prices = pd.Series([100.0, 102.0, 110.0], index=idx)
        eng = _engine({"2026-01-03": "Buy"}, prices, cost_bps=0.0, ticker="AAPL")
        result = eng.run()
        # Executes at the 01-02 close (102), captures the move to 110.
        assert result.decisions[0]["exec_date"] == "2026-01-02"
        assert result.metrics["total_return"] == pytest.approx(8 / 102)


@pytest.mark.unit
class TestHitRate:
    def test_hit_rate_and_hold_excluded(self):
        prices = _prices("2026-01-01", [100, 110, 120, 110, 100])
        eng = _engine(
            {"2026-01-01": "Buy", "2026-01-03": "Sell", "2026-01-05": "Hold"},
            prices, cadence_days=2, cost_bps=0.0,
        )
        result = eng.run()
        m = result.metrics
        # Buy at 100 -> next exec at 120: correct. Sell at 120 -> end 100: correct.
        assert m["n_decisions"] == 3
        assert m["n_directional"] == 2
        assert m["hit_rate"] == pytest.approx(1.0)

    def test_wrong_directional_call_counted(self):
        prices = _prices("2026-01-01", [100, 90])
        eng = _engine({"2026-01-01": "Buy"}, prices, cost_bps=0.0)
        result = eng.run()
        assert result.metrics["hit_rate"] == pytest.approx(0.0)


@pytest.mark.unit
class TestResumeAndRobustness:
    def test_decisions_persist_and_resume_skips_llm(self, tmp_path):
        prices = _prices("2026-01-01", [100, 101, 102])
        path = tmp_path / "decisions.jsonl"
        calls = []

        def decide(t, d):
            calls.append(d)
            return "Buy"

        eng = BacktestEngine(
            "BTC-USD", "2026-01-01", "2026-01-03", cadence_days=2,
            decide_fn=decide, price_loader=lambda t, s, e: prices,
            decisions_path=path,
        )
        eng.run()
        assert len(calls) == 2
        # Second run must reuse the persisted decisions, not re-decide.
        eng2 = BacktestEngine(
            "BTC-USD", "2026-01-01", "2026-01-03", cadence_days=2,
            decide_fn=lambda t, d: pytest.fail("should not re-decide"),
            price_loader=lambda t, s, e: prices,
            decisions_path=path,
        )
        result = eng2.run()
        assert result.metrics["n_decisions"] == 2
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        assert all(r["rating"] == "Buy" for r in rows)

    def test_failed_decisions_skipped_not_fatal(self):
        prices = _prices("2026-01-01", [100, 105, 110])

        def decide(t, d):
            if d == "2026-01-01":
                raise ValueError("LLM exploded")
            return "Buy"

        eng = BacktestEngine(
            "BTC-USD", "2026-01-01", "2026-01-03", cadence_days=2,
            decide_fn=decide, price_loader=lambda t, s, e: prices,
        )
        result = eng.run()
        assert result.metrics["n_decisions"] == 1
        assert result.decisions[0]["date"] == "2026-01-03"

    def test_unknown_rating_skipped(self):
        prices = _prices("2026-01-01", [100, 105])
        eng = BacktestEngine(
            "BTC-USD", "2026-01-01", "2026-01-01",
            decide_fn=lambda t, d: "Moon",
            price_loader=lambda t, s, e: prices,
        )
        with pytest.raises(ValueError, match="no usable decisions"):
            eng.run()

    def test_requires_decide_fn(self):
        with pytest.raises(ValueError, match="decide_fn"):
            BacktestEngine("BTC-USD", "2026-01-01", "2026-01-02", decide_fn=None)


@pytest.mark.unit
class TestReport:
    def test_report_renders_and_saves(self, tmp_path):
        prices = _prices("2026-01-01", [100, 110, 105])
        eng = _engine(
            {"2026-01-01": "Buy", "2026-01-03": "Underweight"}, prices,
            cadence_days=2,
        )
        result = eng.run()
        md = render_markdown(result)
        assert "Backtest: BTC-USD" in md
        assert "Buy & Hold" in md
        assert "Data integrity caveats" in md
        assert "NOT point-in-time" in md

        md_path, json_path = save_report(result, tmp_path)
        assert md_path.exists() and json_path.exists()
        payload = json.loads(json_path.read_text())
        assert payload["metrics"]["n_decisions"] == 2
        assert len(payload["equity"]) == 3


# ---------------------------------------------------------------------------
# Blind technical mode: anonymization and decision parsing
# ---------------------------------------------------------------------------


def _ohlcv(start, n, base=50000.0, drift=1.002):
    idx = pd.date_range(start=start, periods=n, freq="D")
    close = pd.Series([base * drift**i for i in range(n)], index=idx)
    return pd.DataFrame({
        "Open": close * 0.99,
        "High": close * 1.01,
        "Low": close * 0.98,
        "Close": close,
        "Volume": pd.Series([1e9 + 1e7 * i for i in range(n)], index=idx),
    })


@pytest.mark.unit
class TestBlindView:
    def test_no_identifying_information_leaks(self):
        from tradingagents.backtest.blind import prepare_blind_view
        view = prepare_blind_view(_ohlcv("2025-10-01", 200), "2026-04-10")
        # No ticker, no calendar dates, no absolute price levels.
        assert "BTC" not in view and "USD" not in view
        assert "2025" not in view and "2026" not in view
        assert "50000" not in view and "50,000" not in view
        # Bars are labelled by relative offset and rebased to 100.
        assert "day 0" in view and "day -179" in view
        assert "rebased to 100" in view

    def test_lookahead_excluded(self):
        from tradingagents.backtest.blind import prepare_blind_view
        df = _ohlcv("2026-01-01", 120)
        # Spike after the decision date must not appear in the view.
        df.loc[df.index[-1], "Close"] = 9_999_999.0
        view = prepare_blind_view(df, str(df.index[-2].date()))
        assert "9999999" not in view.replace(",", "")

    def test_rebase_normalises_first_close(self):
        from tradingagents.backtest.blind import prepare_blind_view
        # Two assets at wildly different price levels produce the same view.
        a = prepare_blind_view(_ohlcv("2026-01-01", 60, base=50000.0), "2026-03-01")
        b = prepare_blind_view(_ohlcv("2026-01-01", 60, base=0.37), "2026-03-01")
        assert a == b

    def test_insufficient_history_raises(self):
        from tradingagents.backtest.blind import prepare_blind_view
        with pytest.raises(ValueError, match="at least 30 bars"):
            prepare_blind_view(_ohlcv("2026-01-01", 10), "2026-01-10")


@pytest.mark.unit
class TestBlindDecideFn:
    def _llm(self, reply):
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.invoke.return_value.content = reply
        return llm

    def test_returns_parsed_rating_and_hides_ticker(self):
        from tradingagents.backtest.blind import make_blind_decide_fn
        llm = self._llm("Uptrend with momentum.\nRating: Overweight")
        decide = make_blind_decide_fn(
            llm, ohlcv_loader=lambda t, s, e: _ohlcv("2025-10-01", 250)
        )
        assert decide("BTC-USD", "2026-04-01") == "Overweight"
        # The ticker must never reach the LLM.
        for call in llm.invoke.call_args_list:
            for _role, content in call.args[0]:
                assert "BTC" not in content

    def test_unparseable_reply_raises(self):
        from tradingagents.backtest.blind import make_blind_decide_fn
        decide = make_blind_decide_fn(
            self._llm("To the moon!"),
            ohlcv_loader=lambda t, s, e: _ohlcv("2025-10-01", 250),
        )
        with pytest.raises(ValueError, match="no parseable rating"):
            decide("BTC-USD", "2026-04-01")

    def test_ohlcv_fetched_once_per_ticker(self):
        from tradingagents.backtest.blind import make_blind_decide_fn
        loads = []

        def loader(t, s, e):
            loads.append(t)
            return _ohlcv("2025-10-01", 250)

        decide = make_blind_decide_fn(
            self._llm("Rating: Hold"), ohlcv_loader=loader
        )
        decide("BTC-USD", "2026-04-01")
        decide("BTC-USD", "2026-04-08")
        assert loads == ["BTC-USD"]

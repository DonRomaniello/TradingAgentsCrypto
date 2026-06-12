"""Tests for crypto-pair detection and crypto-aware behavior.

Covers:
- ``is_crypto_pair`` heuristic
- equity-only data tools returning explicit not-applicable messages for crypto
- benchmark selection (BTC-USD for crypto, SPY for equities, self-benchmark
  suppressed)
- calendar-window return alignment (24/7 vs trading-day calendars)
"""

from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.utils import is_crypto_pair


@pytest.mark.unit
class TestIsCryptoPair:
    def test_common_crypto_pairs(self):
        for t in ["BTC-USD", "ETH-USD", "SOL-USDT", "DOGE-USDC", "eth-eur"]:
            assert is_crypto_pair(t), t

    def test_equities_and_indices(self):
        for t in ["AAPL", "RY.TO", "BARC.L", "^GSPC", "SPY", "BRK-B"]:
            assert not is_crypto_pair(t), t

    def test_non_string(self):
        assert not is_crypto_pair(None)
        assert not is_crypto_pair(123)


@pytest.mark.unit
class TestCryptoToolGating:
    def test_financial_statements_not_applicable(self):
        from tradingagents.agents.utils.fundamental_data_tools import (
            get_balance_sheet, get_cashflow, get_income_statement,
        )
        for tool_fn in (get_balance_sheet, get_cashflow, get_income_statement):
            out = tool_fn.invoke({"ticker": "BTC-USD"})
            assert "not applicable" in out
            assert "crypto" in out

    def test_insider_transactions_not_applicable(self):
        from tradingagents.agents.utils.news_data_tools import get_insider_transactions
        out = get_insider_transactions.invoke({"ticker": "ETH-USD"})
        assert "not applicable" in out

    def test_instrument_context_is_crypto_aware(self):
        from tradingagents.agents.utils.agent_utils import build_instrument_context
        crypto_ctx = build_instrument_context("BTC-USD")
        assert "24/7" in crypto_ctx
        equity_ctx = build_instrument_context("AAPL")
        assert "exchange suffix" in equity_ctx


@pytest.mark.unit
class TestBenchmarkSelection:
    def _bench(self, ticker, config=None):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        stub = SimpleNamespace(config=config or {})
        return TradingAgentsGraph._benchmark_ticker(stub, ticker)

    def test_crypto_benchmarked_against_btc(self):
        assert self._bench("ETH-USD") == "BTC-USD"

    def test_equity_benchmarked_against_spy(self):
        assert self._bench("AAPL") == "SPY"

    def test_self_benchmark_suppressed(self):
        assert self._bench("BTC-USD") is None
        assert self._bench("SPY") is None

    def test_config_override(self):
        assert self._bench("ETH-USD", {"benchmark_ticker": "ETH-BTC"}) == "ETH-BTC"


@pytest.mark.unit
class TestWindowReturn:
    def _history(self, dates, closes):
        return pd.DataFrame(
            {"Close": closes}, index=pd.DatetimeIndex(pd.to_datetime(dates))
        )

    def test_calendar_alignment_skips_weekend_gap(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        # Equity series: Friday then Monday-Wednesday (weekend gap).
        hist = self._history(
            ["2026-06-05", "2026-06-08", "2026-06-09", "2026-06-10"],
            [100.0, 102.0, 103.0, 110.0],
        )
        start = datetime(2026, 6, 5)
        target = datetime(2026, 6, 10)  # 5 calendar days
        ret, entry, exit_ = TradingAgentsGraph._window_return(hist, start, target)
        assert ret == pytest.approx(0.10)
        assert entry == datetime(2026, 6, 5)
        assert exit_ == datetime(2026, 6, 10)

    def test_exit_capped_at_target_date(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        # Buffer rows past the target must not be used as the exit bar.
        hist = self._history(
            ["2026-06-05", "2026-06-08", "2026-06-12"],
            [100.0, 105.0, 200.0],
        )
        ret, _, exit_ = TradingAgentsGraph._window_return(
            hist, datetime(2026, 6, 5), datetime(2026, 6, 10)
        )
        assert ret == pytest.approx(0.05)
        assert exit_ == datetime(2026, 6, 8)

    def test_insufficient_data_returns_none(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        hist = self._history(["2026-06-05"], [100.0])
        assert TradingAgentsGraph._window_return(
            hist, datetime(2026, 6, 5), datetime(2026, 6, 10)
        ) is None


@pytest.mark.unit
class TestCryptoDataTools:
    def test_binance_perp_symbol_mapping(self):
        from tradingagents.dataflows.crypto_utils import binance_perp_symbol
        assert binance_perp_symbol("BTC-USD") == "BTCUSDT"
        assert binance_perp_symbol("eth-usdt") == "ETHUSDT"
        assert binance_perp_symbol("SOL-USDC") == "SOLUSDT"
        assert binance_perp_symbol("ETH-BTC") is None
        assert binance_perp_symbol("AAPL") is None

    def test_derivatives_tools_reject_equities(self):
        from tradingagents.agents.utils.crypto_data_tools import (
            get_funding_rates, get_open_interest,
        )
        out = get_funding_rates.invoke({"ticker": "AAPL", "curr_date": "2026-06-01"})
        assert "not a crypto pair" in out
        out = get_open_interest.invoke({"ticker": "AAPL", "curr_date": "2026-06-01"})
        assert "not a crypto pair" in out

    def test_funding_rates_formats_response(self, monkeypatch):
        from tradingagents.dataflows import crypto_utils

        class _Resp:
            def raise_for_status(self):
                pass
            def json(self):
                return [
                    {"fundingRate": "0.0001", "fundingTime": 1},
                    {"fundingRate": "0.0003", "fundingTime": 2},
                ]

        monkeypatch.setattr(crypto_utils.requests, "get", lambda *a, **k: _Resp())
        out = crypto_utils.get_funding_rates("BTC-USD", "2026-06-01")
        assert "BTCUSDT" in out
        assert "+0.0300%" in out  # latest rate 0.0003
        assert "annualised" in out

    def test_fear_greed_filters_future_values(self, monkeypatch):
        from tradingagents.dataflows import crypto_utils

        class _Resp:
            def raise_for_status(self):
                pass
            def json(self):
                # One value inside the window, one in the future (look-ahead).
                return {"data": [
                    {"timestamp": "1748736000", "value": "20", "value_classification": "Extreme Fear"},  # 2025-06-01
                    {"timestamp": "1780272000", "value": "90", "value_classification": "Extreme Greed"},  # 2026-06-01
                ]}

        monkeypatch.setattr(crypto_utils.requests, "get", lambda *a, **k: _Resp())
        out = crypto_utils.get_fear_greed_index("2025-06-05", look_back_days=14)
        assert "20" in out and "Extreme Fear" in out
        assert "90" not in out  # future value must not leak into a historical run

    def test_api_failure_degrades_gracefully(self, monkeypatch):
        from tradingagents.dataflows import crypto_utils

        def _boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(crypto_utils.requests, "get", _boom)
        assert "No funding rate data" in crypto_utils.get_funding_rates("BTC-USD", "2026-06-01")
        assert "unavailable" in crypto_utils.get_open_interest("BTC-USD", "2026-06-01")
        assert "unavailable" in crypto_utils.get_fear_greed_index("2026-06-01")


@pytest.mark.unit
class TestRatingDistance:
    def test_distance_and_consistency(self):
        from tradingagents.agents.utils.rating import rating_distance
        assert rating_distance("Buy", "Buy") == 0
        assert rating_distance("Buy", "Hold") == 2
        assert rating_distance("Sell", "Buy") == 4
        assert rating_distance("Buy", None) is None
        assert rating_distance("Buy", "Strong Buy") is None

    def test_divergence_warning_logged(self, caplog):
        import logging
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        stub = SimpleNamespace(ticker="BTC-USD")
        state = {
            "investment_plan": "Rating: Sell\nThesis broken.",
            "final_trade_decision": "**Rating**: Buy\nAggressive entry.",
        }
        with caplog.at_level(logging.WARNING):
            TradingAgentsGraph._check_rating_consistency(stub, state)
        assert any("Rating divergence" in r.message for r in caplog.records)

    def test_no_warning_when_adjacent(self, caplog):
        import logging
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        stub = SimpleNamespace(ticker="BTC-USD")
        state = {
            "investment_plan": "Rating: Buy",
            "final_trade_decision": "**Rating**: Overweight",
        }
        with caplog.at_level(logging.WARNING):
            TradingAgentsGraph._check_rating_consistency(stub, state)
        assert not any("Rating divergence" in r.message for r in caplog.records)

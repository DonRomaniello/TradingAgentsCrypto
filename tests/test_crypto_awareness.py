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

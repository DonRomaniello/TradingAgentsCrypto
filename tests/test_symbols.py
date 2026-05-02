"""Tests for the crypto symbol model (parse_symbol / format_symbol / Instrument)."""

import pytest

from tradingagents.dataflows.symbols import Instrument, format_symbol, parse_symbol


@pytest.mark.unit
class TestParseSymbol:
    def test_basic_slash_pair(self):
        i = parse_symbol("BTC/USDT")
        assert i == Instrument(base="BTC", quote="USDT", venue=None)

    def test_dash_pair_normalised(self):
        i = parse_symbol("BTC-USD")
        assert i == Instrument(base="BTC", quote="USD", venue=None)

    def test_venue_prefix(self):
        i = parse_symbol("binance:BTC/USDT")
        assert i == Instrument(base="BTC", quote="USDT", venue="binance")

    def test_lowercase_input_normalised(self):
        i = parse_symbol("eth/usdt")
        assert i.base == "ETH"
        assert i.quote == "USDT"

    def test_venue_lowercased(self):
        i = parse_symbol("Binance:ETH/USDT")
        assert i.venue == "binance"

    def test_alt_pairs(self):
        for sym in ("SOL/USDT", "DOGE/USDT", "LDO/USDT"):
            i = parse_symbol(sym)
            assert "/" not in i.base
            assert "/" not in i.quote

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_symbol("")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            parse_symbol(None)

    def test_bare_word_raises(self):
        with pytest.raises(ValueError):
            parse_symbol("BTC")

    def test_extra_slash_raises(self):
        with pytest.raises(ValueError):
            parse_symbol("BTC/USDT/EXTRA")


@pytest.mark.unit
class TestFormatSymbol:
    def test_ccxt_no_venue(self):
        i = Instrument(base="BTC", quote="USDT", venue=None)
        assert format_symbol(i) == "BTC/USDT"

    def test_ccxt_with_venue(self):
        i = Instrument(base="BTC", quote="USDT", venue="binance")
        assert format_symbol(i) == "binance:BTC/USDT"

    def test_pair_style_drops_venue(self):
        i = Instrument(base="ETH", quote="USD", venue="coinbase")
        assert format_symbol(i, style="pair") == "ETH/USD"

    def test_round_trip(self):
        for sym in ("BTC/USDT", "ETH/USD", "SOL/USDT"):
            assert format_symbol(parse_symbol(sym)) == sym

    def test_round_trip_with_venue(self):
        sym = "binance:BTC/USDT"
        assert format_symbol(parse_symbol(sym)) == sym

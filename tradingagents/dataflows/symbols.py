from __future__ import annotations

import re
from typing import NamedTuple


class Instrument(NamedTuple):
    base: str
    quote: str
    venue: str | None = None


_PAIR_RE = re.compile(r"^([A-Za-z0-9]+)[/\-]([A-Za-z0-9]+)$")
_VENUE_PAIR_RE = re.compile(r"^([A-Za-z0-9_\-]+):([A-Za-z0-9]+)[/\-]([A-Za-z0-9]+)$")


def parse_symbol(s: str) -> Instrument:
    """Parse a symbol string into an Instrument.

    Accepts:
      - ``BTC/USDT``       → Instrument("BTC", "USDT", None)
      - ``BTC-USD``        → Instrument("BTC", "USD", None)
      - ``binance:BTC/USDT`` → Instrument("BTC", "USDT", "binance")
    """
    if not s or not isinstance(s, str):
        raise ValueError(
            f"Invalid symbol {s!r}. Examples: 'BTC/USDT', 'binance:BTC/USDT', 'ETH-USD'"
        )
    s = s.strip()

    m = _VENUE_PAIR_RE.match(s)
    if m:
        venue, base, quote = m.group(1), m.group(2).upper(), m.group(3).upper()
        return Instrument(base=base, quote=quote, venue=venue.lower())

    m = _PAIR_RE.match(s)
    if m:
        base, quote = m.group(1).upper(), m.group(2).upper()
        return Instrument(base=base, quote=quote, venue=None)

    raise ValueError(
        f"Cannot parse symbol {s!r}. "
        "Expected formats: 'BTC/USDT', 'binance:BTC/USDT', 'ETH-USD'"
    )


def format_symbol(instrument: Instrument, style: str = "ccxt") -> str:
    """Format an Instrument back to a string.

    Styles:
      - ``"ccxt"``  → ``"BTC/USDT"`` or ``"binance:BTC/USDT"`` if venue set
      - ``"pair"``  → ``"BTC/USDT"`` (no venue prefix)
    """
    pair = f"{instrument.base}/{instrument.quote}"
    if style == "ccxt" and instrument.venue:
        return f"{instrument.venue}:{pair}"
    return pair

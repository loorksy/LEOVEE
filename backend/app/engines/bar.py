"""The bar type every deterministic engine computes on.

Two deliberate departures from the shape this started as (which lived inside
``volatility.py`` and carried only OHLC as ``Decimal``):

**It carries time.** Chart annotations anchor on ``{ts, price}`` pairs — a
trendline is two points in time-price space, a zone spans a time range, a swing
high *is* a timestamp. The previous bar had no ``ts`` at all and
``bars_from_candles`` dropped it, so nothing downstream could produce an anchor
even in principle. Every engine ported in M2–M4 needs it, so it is required
rather than optional: a bar without a timestamp is not a bar.

**It computes in float.** The reference implementation is JavaScript, where all
arithmetic is IEEE-754 double. Running the port on ``Decimal`` gives *different*
answers — usually in the last few digits, occasionally at a comparison boundary
that flips a pattern from detected to missed — and the golden fixtures would
flag every one as a diff. ``Decimal`` stays at the money boundary (persisted
entry/stop/target prices, position sizing), and the conversion happens here, at
the edge, rather than being sprinkled through the engines.

See docs/PORTING.md and app/core/numeric.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.core.numeric import to_float

__all__ = ["OHLCBar", "bar_from_candle", "bars_from_candles"]


@dataclass(frozen=True, slots=True)
class OHLCBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    # Forex has no consolidated volume; providers report tick counts and some
    # report nothing. Defaulting to zero keeps the field usable as a weak signal
    # without letting an engine mistake "not reported" for "no activity" — check
    # for a positive value before relying on it.
    volume: float = 0.0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open


class _CandleLike(Protocol):
    ts: Any
    open: Any
    high: Any
    low: Any
    close: Any


def bar_from_candle(candle: _CandleLike) -> OHLCBar:
    """Convert a stored/normalized candle row into an engine bar."""
    volume = getattr(candle, "volume", None)
    return OHLCBar(
        ts=candle.ts,
        open=to_float(candle.open),
        high=to_float(candle.high),
        low=to_float(candle.low),
        close=to_float(candle.close),
        volume=to_float(volume) if volume is not None else 0.0,
    )


def bars_from_candles(candles: list[Any]) -> list[OHLCBar]:
    return [bar_from_candle(candle) for candle in candles]

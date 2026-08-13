"""Bar builders for engine tests.

Every deterministic-engine test needs a series of bars, and the ported engines
care about time as well as price, so hand-rolling ``OHLCBar(...)`` per test file
means repeating timestamp arithmetic that has nothing to do with what is being
tested. These helpers keep the shape in one place and make the *intent* of a
fixture readable — "twenty flat bars", "a rising series" — which is what the
assertion is usually about.

The synthetic-series style mirrors the builders in AiChart's own geometry tests
(``candlesticks.test.ts`` and friends), which were written to pin edge shapes
rather than to look like real market data. Those transfer here almost verbatim
during M2 and M3.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engines.bar import OHLCBar

__all__ = [
    "EPOCH",
    "bar",
    "flat_bars",
    "rising_bars",
    "falling_bars",
    "swinging_bars",
]

# A fixed start time: fixtures must be reproducible, so nothing here reads the
# clock. Golden comparisons would drift on every run otherwise.
EPOCH = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def bar(
    *,
    ts: datetime | None = None,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0.0,
) -> OHLCBar:
    return OHLCBar(
        ts=ts or EPOCH,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _series(
    count: int,
    *,
    start: float,
    step: float,
    spread: float,
    interval: timedelta,
) -> list[OHLCBar]:
    bars: list[OHLCBar] = []
    for i in range(count):
        o = start + i * step
        c = o + step * 0.6 if step else o
        bars.append(
            OHLCBar(
                ts=EPOCH + interval * i,
                open=o,
                high=max(o, c) + spread,
                low=min(o, c) - spread,
                close=c,
                volume=0.0,
            )
        )
    return bars


def rising_bars(
    count: int = 30,
    *,
    start: float = 1.1000,
    step: float = 0.0003,
    spread: float = 0.0002,
    interval: timedelta = timedelta(hours=1),
) -> list[OHLCBar]:
    return _series(count, start=start, step=step, spread=spread, interval=interval)


def falling_bars(
    count: int = 30,
    *,
    start: float = 1.1000,
    step: float = 0.0003,
    spread: float = 0.0002,
    interval: timedelta = timedelta(hours=1),
) -> list[OHLCBar]:
    return _series(count, start=start, step=-step, spread=spread, interval=interval)


def flat_bars(
    count: int = 20,
    *,
    price: float = 1.1000,
    spread: float = 0.0002,
    interval: timedelta = timedelta(hours=1),
) -> list[OHLCBar]:
    return _series(count, start=price, step=0.0, spread=spread, interval=interval)


def swinging_bars(
    legs: int = 12,
    *,
    start: float = 2000.0,
    drift: float = 4.0,
    swing: float = 6.0,
    bars_per_leg: int = 5,
    spread: float = 0.5,
    interval: timedelta = timedelta(minutes=15),
) -> list[OHLCBar]:
    """A trend that actually swings, which a monotonic ramp does not.

    `rising_bars` climbs every bar, so no bar is a local extreme and the swing
    detectors correctly find nothing — a straight line has no structure. Trend
    and level tests need pullbacks, so this walks between alternating turning
    points that each drift by `drift` per cycle: higher highs and higher lows
    for a positive drift, lower ones for a negative drift.

    Two construction details are load-bearing, both learned by getting them
    wrong:

    - the path is *continuous*, each leg starting where the last ended. Building
      legs independently let a pullback begin above the peak it was retracing,
      which is not a pullback;
    - wicks *vary*. A turning price is the close of one bar and the open of the
      next, so a constant wick gives both the same high and they disqualify each
      other under the plateau rule — the series then reads as having no swings
      at all. Real candles have unequal wicks; these do too, deterministically.
    """
    turns: list[float] = []
    for cycle in range(legs):
        base = start + drift * cycle
        turns.append(base)
        turns.append(base + swing)

    path: list[float] = [turns[0]]
    for index in range(len(turns) - 1):
        origin = turns[index]
        target = turns[index + 1]
        for step in range(1, bars_per_leg + 1):
            path.append(origin + (target - origin) * step / bars_per_leg)

    bars: list[OHLCBar] = []
    for index in range(len(path) - 1):
        open_price = path[index]
        close_price = path[index + 1]
        # Deterministic, so fixtures stay reproducible, but uneven enough that
        # two adjacent bars never share an extreme.
        upper = spread * (0.5 + 0.5 * ((index * 7) % 5) / 4)
        lower = spread * (0.5 + 0.5 * ((index * 11) % 5) / 4)
        bars.append(
            OHLCBar(
                ts=EPOCH + interval * index,
                open=open_price,
                high=max(open_price, close_price) + upper,
                low=min(open_price, close_price) - lower,
                close=close_price,
                volume=100.0 + index,
            )
        )
    return bars

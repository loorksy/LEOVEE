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

__all__ = ["EPOCH", "bar", "flat_bars", "rising_bars", "falling_bars"]

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

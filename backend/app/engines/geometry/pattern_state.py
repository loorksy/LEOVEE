"""The shared forming → completed → invalidated state machine.

Every detector reports state through these helpers so that "completed" always
means the same thing: a **close** beyond the boundary by more than 0.25×ATR.

Wicks never complete a pattern. A wick through a level is a sweep — price
reached for the orders resting there and was rejected — and treating it as a
break is how a detector reports a head-and-shoulders completion on the exact
bar that proved the neckline held.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

from app.engines.bar import OHLCBar
from app.engines.geometry.types import PatternStatus

__all__ = [
    "BREAK_BUFFER_ATR",
    "BreakoutCheck",
    "BoundedResolution",
    "first_close_beyond",
    "resolve_bounded_pattern",
    "project_measured_move",
    "state_confidence",
]

BREAK_BUFFER_ATR = 0.25


@dataclass(frozen=True, slots=True)
class BreakoutCheck:
    broken: bool
    break_index: int | None = None
    break_close: float | None = None


@dataclass(frozen=True, slots=True)
class BoundedResolution:
    status: PatternStatus
    break_index: int | None = None
    break_direction: str | None = None


def first_close_beyond(
    bars: list[OHLCBar],
    from_index: int,
    level_at: Callable[[int], float],
    direction: str,
    atr: float,
    buffer: float = BREAK_BUFFER_ATR,
) -> BreakoutCheck:
    """First candle after `from_index` whose close crosses the level."""
    tol = max(atr * buffer, sys.float_info.epsilon)
    for i in range(max(0, from_index + 1), len(bars)):
        close = bars[i].close
        level = level_at(i)
        if not isfinite(level):
            continue
        if direction == "up" and close > level + tol:
            return BreakoutCheck(broken=True, break_index=i, break_close=close)
        if direction == "down" and close < level - tol:
            return BreakoutCheck(broken=True, break_index=i, break_close=close)
    return BreakoutCheck(broken=False)


def resolve_bounded_pattern(
    *,
    bars: list[OHLCBar],
    from_index: int,
    upper_at: Callable[[int], float],
    lower_at: Callable[[int], float],
    atr: float,
    complete_direction: str,
    forming_valid: bool = True,
) -> BoundedResolution:
    """Resolve a two-boundary shape: triangle, wedge, flag body.

    Whichever boundary price closes out of *first* decides the outcome, which
    is why both are checked rather than stopping at the expected one — a
    pattern that breaks the wrong way is invalidated, not still forming.
    """
    up = first_close_beyond(bars, from_index, upper_at, "up", atr)
    down = first_close_beyond(bars, from_index, lower_at, "down", atr)

    first: tuple[str, int] | None = None
    if up.broken and down.broken:
        assert up.break_index is not None and down.break_index is not None
        first = (
            ("up", up.break_index)
            if up.break_index <= down.break_index
            else ("down", down.break_index)
        )
    elif up.broken and up.break_index is not None:
        first = ("up", up.break_index)
    elif down.broken and down.break_index is not None:
        first = ("down", down.break_index)

    if first is not None:
        direction, index = first
        if complete_direction in ("either", direction):
            return BoundedResolution(
                status=PatternStatus.COMPLETED,
                break_index=index,
                break_direction=direction,
            )
        return BoundedResolution(
            status=PatternStatus.INVALIDATED,
            break_index=index,
            break_direction=direction,
        )

    return BoundedResolution(
        status=PatternStatus.FORMING if forming_valid else PatternStatus.INVALIDATED
    )


def project_measured_move(break_level: float, height: float, direction: str) -> float:
    """Measured-move target: the break level plus or minus the pattern height."""
    magnitude = abs(height)
    return break_level + magnitude if direction == "up" else break_level - magnitude


def state_confidence(base: float, status: PatternStatus) -> float:
    """Confidence adjusted for state.

    A completed break is the strongest claim the geometry makes, and an
    invalidated one is nearly worthless as evidence *of that pattern*.

    Forming is deliberately **not** discounted. An earlier version docked it
    15%, which quietly asserted that a structure still building is a worse
    trade — but the boundary of a forming pattern is often the best entry
    available, and a detector has no business pre-judging that. The stage and
    completion ratio travel with the pattern instead, and the decision engine
    weighs them.
    """
    if status is PatternStatus.INVALIDATED:
        return round(base * 0.4)
    return round(base)

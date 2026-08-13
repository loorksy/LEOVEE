"""Rectangles: horizontal consolidation between two flat boundaries.

The shape most detectors quietly misfile. A triangle detector sees converging
lines where there are none; a channel detector wants a slope. A rectangle is
defined by what it *lacks* — slope and convergence — so the test is positional:
at least two highs sitting on one flat line, at least two lows on another, and a
band between them that holds.

Every boundary pivot must sit on its line. One stray pivot means the structure
is something else, and describing it as a rectangle anyway would be the
invented-name failure the doctrine forbids.

Rectangles break both ways, so the direction is read off the break rather than
presumed. A break one way followed by a break the other is a *failed* breakout
and is reported as invalidated — saying that is more useful than pretending the
second break is a fresh completion.
"""

from __future__ import annotations

from app.engines.bar import OHLCBar
from app.engines.geometry.pattern_state import (
    constant_level,
    first_close_beyond,
    project_measured_move,
    state_confidence,
)
from app.engines.geometry.types import (
    PatternInstance,
    PatternStatus,
    PatternType,
    clamp_confidence,
)
from app.engines.primitives.pivots import Pivot

__all__ = ["detect_rectangles"]

#: Boundary flatness: pivots within this many ATR of their shared line.
BOUNDARY_TOLERANCE_ATR = 0.35
#: Minimum band height — flatter than this is noise, not consolidation.
MIN_HEIGHT_ATR = 1.2
MIN_SPAN_BARS = 12
#: A rectangle is a *live* structure; one that ended fifty bars ago is history
#: the trendline pass already carries.
RECENT_PIVOTS = 8


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def detect_rectangles(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float
) -> list[PatternInstance]:
    if atr <= 0 or len(zigzag) < 4:
        return []

    recent = zigzag[-RECENT_PIVOTS:]
    highs = [p for p in recent if p.kind == "high"]
    lows = [p for p in recent if p.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return []

    top = _median([p.price for p in highs])
    bottom = _median([p.price for p in lows])
    height = top - bottom
    if not height >= MIN_HEIGHT_ATR * atr:
        return []

    tolerance = BOUNDARY_TOLERANCE_ATR * atr
    if any(abs(p.price - top) > tolerance for p in highs):
        return []
    if any(abs(p.price - bottom) > tolerance for p in lows):
        return []

    anchors = sorted(recent, key=lambda p: p.index)
    first, last = anchors[0], anchors[-1]
    if last.index - first.index < MIN_SPAN_BARS:
        return []

    up_break = first_close_beyond(bars, last.index, constant_level(top), "up", atr)
    down_break = first_close_beyond(bars, last.index, constant_level(bottom), "down", atr)

    status = PatternStatus.FORMING
    break_direction: str | None = None
    break_index: int | None = None
    if up_break.broken and down_break.broken:
        assert up_break.break_index is not None and down_break.break_index is not None
        status = PatternStatus.INVALIDATED
        first_out = up_break.break_index < down_break.break_index
        break_direction = "up" if first_out else "down"
        break_index = min(up_break.break_index, down_break.break_index)
    elif up_break.broken:
        status = PatternStatus.COMPLETED
        break_direction = "up"
        break_index = up_break.break_index
    elif down_break.broken:
        status = PatternStatus.COMPLETED
        break_direction = "down"
        break_index = down_break.break_index

    break_level = bottom if break_direction == "down" else top
    touches = len(highs) + len(lows)
    base = 55 + min(12.0, (touches - 4) * 3) + min(8.0, (height / atr - MIN_HEIGHT_ATR) * 3)

    return [
        PatternInstance(
            pattern_type=PatternType.RECTANGLE,
            status=status,
            anchors=anchors,
            neckline=((first.ts.timestamp(), break_level), (last.ts.timestamp(), break_level)),
            projected_target=(
                project_measured_move(break_level, height, break_direction)
                if break_direction is not None
                else None
            ),
            break_direction=break_direction,
            break_index=break_index,
            break_level=break_level,
            confidence=clamp_confidence(state_confidence(base, status)),
            evidence=[
                f"band {bottom:.5f}-{top:.5f}",
                f"height={height / atr:.2f}atr",
                f"touches={touches}",
                f"span={last.index - first.index}bars",
            ],
        )
    ]

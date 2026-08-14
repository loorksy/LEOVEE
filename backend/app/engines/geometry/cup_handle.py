"""Cup and handle, and its inverse.

A rounded base between two rim highs at one level, then a shallow pullback — the
handle — that holds the upper part of the cup before the rim breaks. The inverse
mirrors it downward.

This is the shape people most want to see where it is not, so two rules carry
the weight:

1. **The base must be rounded, not a spike.** The bottom sits in the middle
   third of the cup's span. A bottom hugging either rim is a spike-and-recover
   that happens to start and end at the same price.
2. **The handle must hold the upper half of the cup.** A pullback all the way to
   the cup bottom is not a handle — it is the base failing to hold, and calling
   it a handle turns a broken structure into a bullish one.

The depth bound is deliberately generous at the top end. Depth alone does not
make a V; roundedness and the handle rule are what reject spikes, and a
genuinely deep rounded base is a *stronger* cup, not a disqualified one.
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

__all__ = ["detect_cup_handle"]

#: Rim highs within this many ATR of each other.
RIM_TOLERANCE_ATR = 0.6
MIN_DEPTH_ATR = 1.5
MAX_DEPTH_ATR = 12.0
#: Handle retracement of cup depth: beyond this the base did not hold.
MAX_HANDLE_RETRACE = 0.5
MIN_CUP_SPAN_BARS = 10
MIN_HANDLE_BARS = 3
#: The bottom must sit within this band of the cup's span to count as rounded.
ROUNDED_LOW, ROUNDED_HIGH = 0.3, 0.7


def _scan(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float, variant: str
) -> PatternInstance | None:
    rim_kind = "high" if variant == "cup" else "low"

    # [rim, bottom, rim, handle-extreme] — newest first.
    for end in range(len(zigzag) - 1, 2, -1):
        handle = zigzag[end]
        rim2 = zigzag[end - 1]
        base = zigzag[end - 2]
        rim1 = zigzag[end - 3]
        if rim1.kind != rim_kind or rim2.kind != rim_kind:
            continue
        if base.kind == rim_kind or handle.kind == rim_kind:
            continue

        rim_level = max(rim1.price, rim2.price) if variant == "cup" else min(rim1.price, rim2.price)
        if abs(rim1.price - rim2.price) > RIM_TOLERANCE_ATR * atr:
            continue

        depth = abs(rim_level - base.price)
        if depth < MIN_DEPTH_ATR * atr or depth > MAX_DEPTH_ATR * atr:
            continue

        span = rim2.index - rim1.index
        if span < MIN_CUP_SPAN_BARS:
            continue
        base_position = (base.index - rim1.index) / span
        if base_position < ROUNDED_LOW or base_position > ROUNDED_HIGH:
            continue

        handle_retrace = abs(rim_level - handle.price) / depth
        if handle_retrace > MAX_HANDLE_RETRACE:
            continue
        if handle.index - rim2.index < MIN_HANDLE_BARS:
            continue

        break_direction = "up" if variant == "cup" else "down"
        completion = first_close_beyond(
            bars, handle.index, constant_level(rim_level), break_direction, atr
        )
        # Invalidation: the handle deepens past half the cup — the base failed.
        invalidation_level = (
            rim_level - depth * MAX_HANDLE_RETRACE
            if variant == "cup"
            else rim_level + depth * MAX_HANDLE_RETRACE
        )
        invalidation = first_close_beyond(
            bars,
            handle.index,
            constant_level(invalidation_level),
            "down" if variant == "cup" else "up",
            atr,
        )

        status = PatternStatus.FORMING
        break_index: int | None = None
        if completion.broken and invalidation.broken:
            assert completion.break_index is not None and invalidation.break_index is not None
            if invalidation.break_index < completion.break_index:
                status, break_index = PatternStatus.INVALIDATED, invalidation.break_index
            else:
                status, break_index = PatternStatus.COMPLETED, completion.break_index
        elif invalidation.broken:
            status, break_index = PatternStatus.INVALIDATED, invalidation.break_index
        elif completion.broken:
            status, break_index = PatternStatus.COMPLETED, completion.break_index

        score = (
            56
            + min(10.0, (depth / atr) * 2)
            + min(8.0, (1 - handle_retrace / MAX_HANDLE_RETRACE) * 8)
        )
        return PatternInstance(
            pattern_type=(
                PatternType.CUP_AND_HANDLE
                if variant == "cup"
                else PatternType.INVERSE_CUP_AND_HANDLE
            ),
            status=status,
            anchors=[rim1, base, rim2, handle],
            neckline=(
                (rim1.ts.timestamp(), rim_level),
                (handle.ts.timestamp(), rim_level),
            ),
            projected_target=project_measured_move(rim_level, depth, break_direction),
            break_direction=break_direction,
            break_index=break_index,
            break_level=rim_level,
            confidence=clamp_confidence(state_confidence(score, status)),
            evidence=[
                f"rim={rim_level:.5f}",
                f"depth={depth / atr:.2f}atr",
                f"handle_retrace={handle_retrace * 100:.0f}%",
                f"base_position={base_position * 100:.0f}%",
            ],
        )
    return None


def detect_cup_handle(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float
) -> list[PatternInstance]:
    if atr <= 0 or len(zigzag) < 4:
        return []
    found = [_scan(bars, zigzag, atr, variant) for variant in ("cup", "inverse")]
    return [pattern for pattern in found if pattern is not None]

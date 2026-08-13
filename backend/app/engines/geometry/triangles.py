"""Converging-boundary patterns: triangles **and** wedges.

One machinery, one classification table. A wedge is the same construction as a
triangle with both boundary slopes sharing a sign, so a separate detector would
duplicate every line fit, every conformance test and every break rule for the
sake of a different label:

======================  ======================  =======================
upper boundary          lower boundary          pattern
======================  ======================  =======================
flat                    rising                  ascending triangle (up)
falling                 flat                    descending triangle (down)
falling                 rising                  symmetrical triangle (either)
rising                  rising, converging      rising wedge (down)
falling                 falling, converging     falling wedge (up)
======================  ======================  =======================

Boundaries are fitted through the largest recent pivot suffix that conforms,
and status comes from the shared state machine: a **close** beyond a boundary
by more than 0.25xATR, never a wick.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from dataclasses import dataclass

from app.engines.bar import OHLCBar
from app.engines.geometry.pattern_state import (
    project_measured_move,
    resolve_bounded_pattern,
    state_confidence,
)
from app.engines.geometry.types import (
    PatternInstance,
    PatternType,
    clamp_confidence,
    line_price_at_index,
)
from app.engines.primitives.pivots import Pivot

__all__ = ["PATTERN_WINDOW_BARS", "detect_converging_patterns"]

PATTERN_WINDOW_BARS = 150
MIN_BARS = 40
MIN_PIVOTS_PER_SIDE = 2
MAX_SUFFIX_PIVOTS = 6
MIN_BOUNDARY_SPAN_BARS = 8
BOUNDARY_CONFORM_ATR = 0.35
FLAT_SLOPE_ATR_PER_BAR = 0.05
#: Boundaries must have narrowed to at most this share of the start width.
MAX_END_WIDTH_RATIO = 0.8
#: Forming dies once price has consumed this share of the way to the apex.
#: Past it the two boundaries are close enough that "inside the triangle" stops
#: meaning anything — the shape has run out of room without resolving.
APEX_CONSUMED_LIMIT = 0.8


@dataclass(frozen=True, slots=True)
class _BoundaryFit:
    anchors: tuple[Pivot, Pivot]
    slope: float
    pivot_count: int


def _fit_boundary(pivots: list[Pivot], atr: float) -> _BoundaryFit | None:
    """Fit through the largest recent pivot suffix whose members all conform.

    Suffixes are tried newest-first and longest-wins, which makes the fit robust
    to older pre-pattern structure without giving up determinism: a stale
    base-noise pivot simply falls out of the suffix instead of vetoing the whole
    boundary. Every pivot *inside* the accepted suffix must respect the line —
    one rogue middle pivot means the shape is not that boundary, so the fit
    retries shorter rather than averaging the disagreement away.
    """
    tol = max(atr * BOUNDARY_CONFORM_ATR, sys.float_info.epsilon)
    max_suffix = min(len(pivots), MAX_SUFFIX_PIVOTS)

    for size in range(max_suffix, MIN_PIVOTS_PER_SIDE - 1, -1):
        subset = pivots[-size:]
        first = subset[0]
        last = subset[-1]
        if last.index - first.index < MIN_BOUNDARY_SPAN_BARS:
            continue
        if any(abs(p.price - line_price_at_index(first, last, p.index)) > tol for p in subset):
            continue
        return _BoundaryFit(
            anchors=(first, last),
            slope=(last.price - first.price) / max(1, last.index - first.index),
            pivot_count=size,
        )
    return None


def _classify_slope(slope: float, atr: float) -> str:
    per_bar = slope / max(atr, sys.float_info.epsilon)
    if abs(per_bar) < FLAT_SLOPE_ATR_PER_BAR:
        return "flat"
    return "rising" if per_bar > 0 else "falling"


def _classify(upper: str, lower: str, converging: bool) -> tuple[PatternType, str] | None:
    if upper == "flat" and lower == "rising":
        return PatternType.ASCENDING_TRIANGLE, "up"
    if upper == "falling" and lower == "flat":
        return PatternType.DESCENDING_TRIANGLE, "down"
    if upper == "falling" and lower == "rising":
        return PatternType.SYMMETRICAL_TRIANGLE, "either"
    if upper == "rising" and lower == "rising" and converging:
        # Rising wedge: both boundaries climb but the range squeezes, and the
        # resolution is conventionally against the slope.
        return PatternType.WEDGE, "down"
    if upper == "falling" and lower == "falling" and converging:
        return PatternType.WEDGE, "up"
    return None


def detect_converging_patterns(
    bars: list[OHLCBar], pivots: list[Pivot], atr: float
) -> list[PatternInstance]:
    if atr <= 0 or len(bars) < MIN_BARS:
        return []

    window_start = max(0, len(bars) - PATTERN_WINDOW_BARS)
    highs = [p for p in pivots if p.kind == "high" and p.index >= window_start]
    lows = [p for p in pivots if p.kind == "low" and p.index >= window_start]

    upper = _fit_boundary(highs, atr)
    lower = _fit_boundary(lows, atr)
    if upper is None or lower is None:
        return []

    start_index = max(upper.anchors[0].index, lower.anchors[0].index)
    end_index = max(upper.anchors[1].index, lower.anchors[1].index)

    def upper_at(index: int) -> float:
        return line_price_at_index(upper.anchors[0], upper.anchors[1], index)

    def lower_at(index: int) -> float:
        return line_price_at_index(lower.anchors[0], lower.anchors[1], index)

    start_width = upper_at(start_index) - lower_at(start_index)
    end_width = upper_at(end_index) - lower_at(end_index)
    # A crossed or zero-width pair is not a shape price can sit inside.
    if not start_width > 0 or not end_width > 0:
        return []
    converging = end_width <= start_width * MAX_END_WIDTH_RATIO

    upper_class = _classify_slope(upper.slope, atr)
    lower_class = _classify_slope(lower.slope, atr)
    classified = _classify(upper_class, lower_class, converging)
    if classified is None:
        return []
    pattern_type, expected = classified

    # Symmetrical triangles must actually converge; an expanding megaphone has
    # the same two slope signs and is the opposite structure.
    if not converging and pattern_type not in (
        PatternType.ASCENDING_TRIANGLE,
        PatternType.DESCENDING_TRIANGLE,
    ):
        return []

    width_shrink_per_bar = (start_width - end_width) / max(1, end_index - start_index)
    bars_to_apex = start_width / width_shrink_per_bar if width_shrink_per_bar > 0 else math.inf
    consumed = (len(bars) - 1 - start_index) / bars_to_apex
    forming_valid = consumed <= APEX_CONSUMED_LIMIT

    resolved = resolve_bounded_pattern(
        bars=bars,
        from_index=end_index,
        upper_at=upper_at,
        lower_at=lower_at,
        atr=atr,
        complete_direction=expected,
        forming_valid=forming_valid,
    )

    break_direction = resolved.break_direction or (None if expected == "either" else expected)
    level_at: Callable[[int], float] = lower_at if break_direction == "down" else upper_at
    break_level = level_at(
        resolved.break_index if resolved.break_index is not None else len(bars) - 1
    )

    base = (
        55
        + min(10.0, (upper.pivot_count + lower.pivot_count - 4) * 2.5)
        + min(10.0, (end_index - start_index) / 6)
        + (5 if converging else 0)
    )

    return [
        PatternInstance(
            pattern_type=pattern_type,
            status=resolved.status,
            anchors=[
                upper.anchors[0],
                upper.anchors[1],
                lower.anchors[0],
                lower.anchors[1],
            ],
            projected_target=(
                project_measured_move(break_level, start_width, break_direction)
                if break_direction is not None
                else None
            ),
            break_direction=break_direction,
            break_index=resolved.break_index,
            break_level=break_level,
            confidence=clamp_confidence(state_confidence(base, resolved.status)),
            evidence=[
                f"upper={upper_class}",
                f"lower={lower_class}",
                f"width {start_width:.5f}->{end_width:.5f}",
                f"pivots={upper.pivot_count}+{lower.pivot_count}",
                f"apex consumed={min(consumed, 9.99):.2f}",
            ],
        )
    ]

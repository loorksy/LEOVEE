"""Flags and pennants: an impulse leg, then a shallow counter-trend pause.

The impulse is a net move of at least 2.5xATR over five to ten bars. What
follows is the part that has to be built carefully.

**The consolidation is grown adaptively, bar by bar.** It ends the moment a
close escapes the range built *so far* — and that escaping close is the
breakout (or the invalidation). Measuring a fixed window instead swallows the
breakout candles into the "consolidation", which widens the range past the
shallowness test and rejects the entire structure at the exact moment it becomes
tradeable. The bug is silent: no flag is ever reported, and nothing anywhere
says why.

A flag whose boundaries stay parallel is a flag; one whose late half narrows is
a pennant. Both resolve in the impulse direction, and a close out the other side
invalidates rather than completes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from app.engines.bar import OHLCBar
from app.engines.geometry.pattern_state import (
    BREAK_BUFFER_ATR,
    project_measured_move,
    state_confidence,
)
from app.engines.geometry.types import (
    PatternInstance,
    PatternStatus,
    PatternType,
    clamp_confidence,
)
from app.engines.primitives.pivots import Pivot, PivotKind

__all__ = ["detect_flags"]

IMPULSE_MIN_ATR = 2.5
IMPULSE_MIN_BARS = 5
IMPULSE_MAX_BARS = 10
CONSOLIDATION_MIN_BARS = 3
CONSOLIDATION_MAX_BARS = 20
CONSOLIDATION_MAX_RANGE_ATR = 1.6
MAX_RETRACE_RATIO = 0.6
#: Pennant: the late half of the consolidation is at most this share as wide.
PENNANT_NARROWING_RATIO = 0.6
#: Structures whose resolution is buried deeper than this are history.
MAX_STALENESS_BARS = 10


@dataclass(frozen=True, slots=True)
class _Consolidation:
    end_index: int
    high: float
    low: float
    converging: bool
    resolution: str  # "breakout" | "breakdown" | "open"
    resolution_index: int | None = None


def _build_consolidation(
    bars: list[OHLCBar], start_index: int, direction: str, atr: float
) -> _Consolidation | None:
    """Grow the range until a close escapes it, or the window closes."""
    tol = max(atr * BREAK_BUFFER_ATR, sys.float_info.epsilon)
    high = float("-inf")
    low = float("inf")
    ranges: list[float] = []
    end = start_index

    def finish(resolution_index: int | None, resolution: str) -> _Consolidation:
        mid = len(ranges) // 2
        early = max(ranges[:mid]) if ranges[:mid] else 0.0
        late = max(ranges[mid:]) if ranges[mid:] else 0.0
        return _Consolidation(
            end_index=end,
            high=high,
            low=low,
            converging=early > 0 and late <= early * PENNANT_NARROWING_RATIO,
            resolution=resolution,
            resolution_index=resolution_index,
        )

    limit = min(len(bars) - 1, start_index + CONSOLIDATION_MAX_BARS)
    for i in range(start_index, limit + 1):
        candle = bars[i]
        if i - start_index >= CONSOLIDATION_MIN_BARS:
            escaped_up = candle.close > high + tol
            escaped_down = candle.close < low - tol
            if direction == "up":
                if escaped_up:
                    return finish(i, "breakout")
                if escaped_down:
                    return finish(i, "breakdown")
            else:
                if escaped_down:
                    return finish(i, "breakout")
                if escaped_up:
                    return finish(i, "breakdown")
        high = max(high, candle.high)
        low = min(low, candle.low)
        ranges.append(candle.high - candle.low)
        end = i

    if end - start_index < CONSOLIDATION_MIN_BARS:
        return None
    return finish(None, "open")


def detect_flags(bars: list[OHLCBar], atr: float) -> list[PatternInstance]:
    if atr <= 0 or len(bars) < IMPULSE_MIN_BARS + 8:
        return []

    # Newest first: the most recent valid structure wins, because an older one
    # has already resolved and the trendline pass carries whatever it left.
    for impulse_end in range(len(bars) - CONSOLIDATION_MIN_BARS - 1, IMPULSE_MIN_BARS - 1, -1):
        for span in range(IMPULSE_MIN_BARS, IMPULSE_MAX_BARS + 1):
            impulse_start = impulse_end - span
            if impulse_start < 0:
                break
            origin = bars[impulse_start]
            peak = bars[impulse_end]
            net = peak.close - origin.open
            if abs(net) < IMPULSE_MIN_ATR * atr:
                continue
            direction = "up" if net > 0 else "down"

            consolidation = _build_consolidation(bars, impulse_end, direction, atr)
            if consolidation is None:
                continue
            if consolidation.high - consolidation.low > CONSOLIDATION_MAX_RANGE_ATR * atr:
                continue

            # Shallow retracement only — a deep pullback is a reversal attempt.
            retrace = (
                (peak.close - consolidation.low) / abs(net)
                if direction == "up"
                else (consolidation.high - peak.close) / abs(net)
            )
            if retrace > MAX_RETRACE_RATIO:
                continue

            if consolidation.resolution == "breakout":
                status = PatternStatus.COMPLETED
            elif consolidation.resolution == "breakdown":
                status = PatternStatus.INVALIDATED
            else:
                status = (
                    PatternStatus.INVALIDATED
                    if len(bars) - 1 - impulse_end > CONSOLIDATION_MAX_BARS
                    else PatternStatus.FORMING
                )

            last_relevant = (
                consolidation.resolution_index
                if consolidation.resolution_index is not None
                else len(bars) - 1
            )
            if len(bars) - 1 - last_relevant > MAX_STALENESS_BARS:
                continue

            boundary = consolidation.high if direction == "up" else consolidation.low
            base = (
                56
                + min(12.0, (abs(net) / atr - IMPULSE_MIN_ATR) * 4)
                + min(8.0, (1 - retrace) * 10)
            )
            pole_kind: PivotKind = "low" if direction == "up" else "high"
            peak_kind: PivotKind = "high" if direction == "up" else "low"
            return [
                PatternInstance(
                    pattern_type=(
                        PatternType.PENNANT if consolidation.converging else PatternType.FLAG
                    ),
                    status=status,
                    anchors=[
                        Pivot(
                            index=impulse_start,
                            ts=origin.ts,
                            price=origin.low if direction == "up" else origin.high,
                            kind=pole_kind,
                        ),
                        Pivot(
                            index=impulse_end,
                            ts=peak.ts,
                            price=peak.high if direction == "up" else peak.low,
                            kind=peak_kind,
                        ),
                        Pivot(
                            index=consolidation.end_index,
                            ts=bars[consolidation.end_index].ts,
                            price=(consolidation.low if direction == "up" else consolidation.high),
                            kind=pole_kind,
                        ),
                    ],
                    projected_target=project_measured_move(boundary, abs(net), direction),
                    break_direction=direction,
                    break_index=consolidation.resolution_index,
                    break_level=boundary,
                    confidence=clamp_confidence(state_confidence(base, status)),
                    evidence=[
                        f"impulse={abs(net) / atr:.2f}atr/{span}bars",
                        f"retrace={retrace * 100:.0f}%",
                        "converging (pennant)" if consolidation.converging else "parallel (flag)",
                    ],
                )
            ]
    return []

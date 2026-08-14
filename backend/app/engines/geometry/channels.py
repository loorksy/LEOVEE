"""Channels: a parallel boundary fitted against an accepted trendline.

A channel is not a second line found independently — it is *the same* line
offset until it meets the opposite side. Fitting both boundaries separately
produces two lines that almost never end up parallel, and the resulting shape
says nothing about the containment a trader means by "channel".

So each accepted trendline becomes a base, the opposite-side pivots inside its
span vote on an offset, and the extreme vote is the boundary candidate. It is
accepted when at least two opposite pivots sit within 0.15xATR of that offset
line and the width falls between 1 and 8 ATR: below one ATR the two boundaries
are within a single bar's noise of each other, above eight they are describing
two different structures rather than one channel.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from app.engines.geometry.types import (
    Channel,
    Trendline,
    clamp_confidence,
    line_price_at_index,
)
from app.engines.primitives.pivots import Pivot, PivotKind

__all__ = ["MAX_CHANNELS", "detect_channels"]

OPPOSITE_TOUCH_TOLERANCE_ATR = 0.15
MIN_WIDTH_ATR = 1.0
MAX_WIDTH_ATR = 8.0
MIN_OPPOSITE_TOUCHES = 2
#: Slope below this (ATR per bar) reads as a horizontal channel.
HORIZONTAL_SLOPE_ATR_PER_BAR = 0.03
#: Bounded output contract (detectGeometry): one channel, the strongest.
MAX_CHANNELS = 1


@dataclass(frozen=True, slots=True)
class _Offset:
    pivot: Pivot
    offset: float


def detect_channels(
    pivots: list[Pivot],
    trendlines: list[Trendline],
    atr: float,
) -> list[Channel]:
    if atr <= 0:
        return []

    out: list[Channel] = []
    for base in trendlines:
        opposite_kind: PivotKind = "high" if base.side == "support" else "low"
        a, b = base.anchors
        opposite = [p for p in pivots if p.kind == opposite_kind and a.index <= p.index <= b.index]
        if len(opposite) < MIN_OPPOSITE_TOUCHES:
            continue

        offsets = [
            _Offset(pivot=p, offset=p.price - line_price_at_index(a, b, p.index)) for p in opposite
        ]
        # The extreme offset is the boundary candidate. Reduced rather than
        # sorted so ties keep the earliest pivot, which keeps the snapshot
        # deterministic under equal offsets.
        boundary = offsets[0]
        for candidate in offsets[1:]:
            better = (
                candidate.offset > boundary.offset
                if base.side == "support"
                else candidate.offset < boundary.offset
            )
            if better:
                boundary = candidate

        width_atr = abs(boundary.offset) / atr
        if width_atr < MIN_WIDTH_ATR or width_atr > MAX_WIDTH_ATR:
            continue

        tol = max(atr * OPPOSITE_TOUCH_TOLERANCE_ATR, sys.float_info.epsilon)
        touching = [o for o in offsets if abs(o.offset - boundary.offset) <= tol]
        if len(touching) < MIN_OPPOSITE_TOUCHES:
            continue

        # Anchored at the base anchors' bar positions, so the two boundaries
        # share an x-span and the drawn shape closes.
        parallel = (
            Pivot(index=a.index, ts=a.ts, price=a.price + boundary.offset, kind=opposite_kind),
            Pivot(index=b.index, ts=b.ts, price=b.price + boundary.offset, kind=opposite_kind),
        )

        slope_atr_per_bar = base.slope / atr
        if abs(slope_atr_per_bar) < HORIZONTAL_SLOPE_ATR_PER_BAR:
            direction = "horizontal"
        elif base.slope > 0:
            direction = "rising"
        else:
            direction = "falling"

        out.append(
            Channel(
                direction=direction,
                base=base,
                parallel=parallel,
                width_atr=width_atr,
                opposite_touches=len(touching),
                confidence=clamp_confidence(
                    base.confidence * 0.6 + len(touching) * 10 + min(10.0, width_atr * 2)
                ),
                evidence=[
                    f"base={base.side}",
                    f"width={width_atr:.1f}atr",
                    f"{len(touching)} opposite touches",
                ],
            )
        )

    out.sort(key=lambda c: -c.confidence)
    return out[:MAX_CHANNELS]

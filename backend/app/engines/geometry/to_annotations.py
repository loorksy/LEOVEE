"""Geometry snapshot → renderer-neutral chart annotations.

The one bridge between what the engine *found* and what the chart *draws*, and
it exists so those two can never disagree. A trendline the narrative cites and a
trendline the user sees are the same object, anchored at the same two pivots,
carrying the same confidence — because both come from here.

**Anchors are `{ts, price}` pairs, never bar indices.** An index is meaningless
to a renderer that paginates its own data, and it silently becomes wrong the
moment the window scrolls. This is why `OHLCBar` had to gain a timestamp before
any of this was possible.

**A forming pattern is drawn dashed.** The only visual distinction here that is
semantic rather than cosmetic: the structure has not happened yet, and drawing
it solid asserts something that does not exist. `status` and `stage` stay
separate all the way to the renderer for the same reason they are separate in
the detector.

**No MT5 vocabulary (D3).** The reference emitted the same drawings to a
terminal as well, which is why its type list carried twenty-seven native shapes.
Leovee connects to no terminal, and keeping the vocabulary would leave a hole
shaped exactly like broker integration.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.engines.geometry.types import (
    Channel,
    GeometrySnapshot,
    PatternInstance,
    PatternStatus,
    Trendline,
)
from app.engines.primitives.pivots import Pivot
from app.schemas.chart import (
    ChartAnchor,
    ChartGeometry,
    ChartSemanticOperation,
    ChartSemanticRole,
    ChartSemanticType,
    ChartStyle,
)

__all__ = ["geometry_to_annotations", "summarize_geometry"]

#: Buy/sell colours mean *direction of a trade* and nothing else (M10's rule).
#: Here they mean side of structure, which is the same axis: a support line is
#: where a long is defended.
_SUPPORT_COLOUR = "#22c55e"
_RESISTANCE_COLOUR = "#ef4444"

#: How far outside the pattern the synthetic lead-in and exit points sit, as a
#: fraction of its own span.
_HS_SHOULDER_PAD = 0.08

_HEAD_AND_SHOULDERS = ("head_and_shoulders", "inverse_head_and_shoulders")


def _anchor(pivot: Pivot, timeframe: str | None) -> ChartAnchor:
    return ChartAnchor(ts=pivot.ts.isoformat(), price=float(pivot.price), timeframe=timeframe)


def _point(ts: datetime, price: float, timeframe: str | None) -> ChartAnchor:
    return ChartAnchor(ts=ts.isoformat(), price=float(price), timeframe=timeframe)


def _from_epoch(seconds: float) -> datetime:
    """Necklines are stored as ``(epoch_seconds, price)`` pairs.

    A float, not a datetime, because a neckline is derived geometry — a line
    between two computed points rather than two observed pivots — and the
    detectors build it from ``ts.timestamp()``. Converting here, once, keeps the
    annotation layer speaking only in timestamps.
    """
    return datetime.fromtimestamp(seconds, tz=UTC)


def _trendline(line: Trendline, timeframe: str | None) -> ChartSemanticOperation:
    support = line.side == "support"
    return ChartSemanticOperation(
        semantic_type=ChartSemanticType.TREND_LINE,
        role=ChartSemanticRole.SUPPORT if support else ChartSemanticRole.RESISTANCE,
        confidence=line.confidence,
        geometry=ChartGeometry(
            anchors=[_anchor(pivot, timeframe) for pivot in line.anchors],
            metadata={
                "side": line.side,
                "touches": line.touches,
                "slope": line.slope,
                "price_at_last_bar": line.price_at_last_bar,
                "broken": line.broken,
                "evidence": list(line.evidence),
            },
        ),
        style=ChartStyle(
            color=_SUPPORT_COLOUR if support else _RESISTANCE_COLOUR,
            line_width=2,
            # A broken line is history. Drawn dashed so it reads as something
            # that used to hold, rather than a level still being defended.
            line_style="dashed" if line.broken else "solid",
        ),
    )


def _channel(channel: Channel, timeframe: str | None) -> ChartSemanticOperation:
    base_a, base_b = channel.base.anchors[0], channel.base.anchors[-1]
    parallel_a, parallel_b = channel.parallel
    return ChartSemanticOperation(
        semantic_type=ChartSemanticType.PARALLEL_CHANNEL,
        role=ChartSemanticRole.CHANNEL,
        pattern_type="channel",
        confidence=channel.confidence,
        geometry=ChartGeometry(
            # Four points, base pair first. The order is the contract: a
            # renderer builds the parallel from points three and four, and
            # shuffling them draws a bow tie.
            anchors=[
                _anchor(base_a, timeframe),
                _anchor(base_b, timeframe),
                _anchor(parallel_a, timeframe),
                _anchor(parallel_b, timeframe),
            ],
            metadata={
                "direction": channel.direction,
                "width_atr": channel.width_atr,
                "opposite_touches": channel.opposite_touches,
            },
        ),
        style=ChartStyle(fill_opacity=0.08, line_width=1),
    )


def _pattern_anchors(pattern: PatternInstance, timeframe: str | None) -> list[ChartAnchor]:
    """The pattern's own pivots, plus lead-in and exit for head-and-shoulders.

    A head-and-shoulders tool wants seven points — lead-in, left shoulder,
    trough, head, trough, right shoulder, exit — and the detector produces five.
    Synthesising the outer two on the neckline lets a renderer use its native
    tool; without them it falls back to a generic polyline, which draws the same
    shape while losing the neckline the tool would have derived.
    """
    anchors = [_anchor(pivot, timeframe) for pivot in pattern.anchors]
    if (
        pattern.pattern_type.value not in _HEAD_AND_SHOULDERS
        or len(pattern.anchors) != 5
        or pattern.neckline is None
    ):
        return anchors

    first = pattern.anchors[0]
    last = pattern.anchors[-1]
    span = max(1.0, (last.ts - first.ts).total_seconds())
    pad = span * _HS_SHOULDER_PAD
    (_, from_price), (_, to_price) = pattern.neckline

    return [
        _point(first.ts - timedelta(seconds=pad), from_price, timeframe),
        *anchors,
        _point(last.ts + timedelta(seconds=pad), to_price, timeframe),
    ]


def _pattern(pattern: PatternInstance, timeframe: str | None) -> list[ChartSemanticOperation]:
    forming = pattern.status is PatternStatus.FORMING
    operations = [
        ChartSemanticOperation(
            semantic_type=ChartSemanticType.POLYLINE_PATTERN,
            role=ChartSemanticRole.PATTERN,
            pattern_type=pattern.pattern_type.value,
            confidence=pattern.confidence,
            geometry=ChartGeometry(
                anchors=_pattern_anchors(pattern, timeframe),
                metadata={
                    # Two axes, kept apart all the way to the renderer. `status`
                    # is whether it happened; `stage` is how far along it is.
                    # Collapsing them loses "nearly complete, unconfirmed",
                    # which is the state a reader most needs to see.
                    "status": pattern.status.value,
                    "stage": pattern.stage.value if pattern.stage else None,
                    "completion_ratio": pattern.completion_ratio,
                    "break_direction": pattern.break_direction,
                    "break_level": pattern.break_level,
                    "projected_target": pattern.projected_target,
                    "evidence": list(pattern.evidence),
                },
            ),
            style=ChartStyle(line_style="dashed" if forming else "solid", line_width=2),
        )
    ]

    if pattern.neckline is not None:
        (from_seconds, from_price), (to_seconds, to_price) = pattern.neckline
        operations.append(
            ChartSemanticOperation(
                semantic_type=ChartSemanticType.NECKLINE,
                role=ChartSemanticRole.NECKLINE,
                pattern_type=pattern.pattern_type.value,
                confidence=pattern.confidence,
                geometry=ChartGeometry(
                    anchors=[
                        _point(_from_epoch(from_seconds), from_price, timeframe),
                        _point(_from_epoch(to_seconds), to_price, timeframe),
                    ],
                    metadata={"pattern_status": pattern.status.value},
                ),
                # Always dashed: a neckline is a derived level, not a traded one,
                # and drawing it like a trendline invites it to be treated as one.
                style=ChartStyle(line_style="dashed", line_width=1),
            )
        )
    return operations


def geometry_to_annotations(
    snapshot: GeometrySnapshot, *, timeframe: str | None = None
) -> list[ChartSemanticOperation]:
    """Everything the geometry engine found, as annotations a renderer can draw.

    Bounded by the snapshot itself — the detector already caps trendlines,
    channels and patterns (see `detect.py`), so this adds no limits of its own.
    A second cap here would be a second place to change when the first moves.
    """
    operations: list[ChartSemanticOperation] = []
    for line in snapshot.trendlines:
        operations.append(_trendline(line, timeframe))
    for channel in snapshot.channels:
        operations.append(_channel(channel, timeframe))
    for pattern in snapshot.patterns:
        operations.extend(_pattern(pattern, timeframe))
    return operations


def summarize_geometry(snapshot: GeometrySnapshot) -> dict[str, Any]:
    """Numbers and states for the model, never pixels.

    The counterpart to the annotations: the same snapshot, described in prices
    and labels the decision stage can reason about. Both come from one source,
    which is what keeps the narrative and the chart citing the same levels.
    """
    flat_threshold = snapshot.atr * 0.03
    return {
        "trendlines": [
            {
                "side": line.side,
                "price_at_last_bar": round(line.price_at_last_bar, 6),
                "touches": line.touches,
                "slope_sign": (
                    "flat"
                    if abs(line.slope) < flat_threshold
                    else ("rising" if line.slope > 0 else "falling")
                ),
                "broken": line.broken,
                "confidence": line.confidence,
            }
            for line in snapshot.trendlines
        ],
        "channel": (
            {
                "direction": snapshot.channels[0].direction,
                "width_atr": round(snapshot.channels[0].width_atr, 2),
                "confidence": snapshot.channels[0].confidence,
            }
            if snapshot.channels
            else None
        ),
        "patterns": [
            {
                "pattern": pattern.pattern_type.value,
                "status": pattern.status.value,
                "stage": pattern.stage.value if pattern.stage else None,
                "break_direction": pattern.break_direction,
                "projected_target": (
                    round(pattern.projected_target, 6)
                    if pattern.projected_target is not None
                    else None
                ),
                "confidence": pattern.confidence,
            }
            for pattern in snapshot.patterns
        ],
    }

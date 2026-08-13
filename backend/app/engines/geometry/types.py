"""The geometry contract.

Deterministic by contract: the same candles always produce the same snapshot.
That is not a nicety — the snapshot feeds the decision, the drawing and the
model's context, and if it varied between calls those three would disagree
about the same market.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.numeric import js_round
from app.engines.primitives.pivots import Pivot

__all__ = [
    "PatternStatus",
    "PatternStage",
    "PatternType",
    "Trendline",
    "Channel",
    "PatternInstance",
    "CandlestickSignal",
    "GeometrySnapshot",
    "line_price_at_index",
    "clamp_confidence",
]


class PatternStatus(StrEnum):
    FORMING = "forming"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"


class PatternStage(StrEnum):
    """Where a structure is in its own life.

    Distinct from ``PatternStatus``, which only answers whether a boundary has
    been closed beyond. A shape one bar from completing and one that has barely
    started are both "forming", and treating them alike loses the difference
    between an opportunity and a maybe.
    """

    STARTING = "starting"
    FORMING = "forming"
    NEAR_COMPLETION = "near_completion"
    COMPLETED_UNCONFIRMED = "completed_unconfirmed"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class PatternType(StrEnum):
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    INVERSE_HEAD_AND_SHOULDERS = "inverse_head_and_shoulders"
    ASCENDING_TRIANGLE = "ascending_triangle"
    DESCENDING_TRIANGLE = "descending_triangle"
    SYMMETRICAL_TRIANGLE = "symmetrical_triangle"
    WEDGE = "wedge"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIPLE_TOP = "triple_top"
    TRIPLE_BOTTOM = "triple_bottom"
    RECTANGLE = "rectangle"
    CUP_AND_HANDLE = "cup_and_handle"
    BULL_FLAG = "bull_flag"
    BEAR_FLAG = "bear_flag"


@dataclass(frozen=True, slots=True)
class Trendline:
    side: str  # "support" | "resistance"
    anchors: tuple[Pivot, Pivot]
    #: Price change per bar.
    slope: float
    touches: int
    candle_separation: int
    #: The line extended to the last candle.
    price_at_last_bar: float
    broken: bool
    confidence: int
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "anchors": [_pivot_dict(p) for p in self.anchors],
            "slope": self.slope,
            "touches": self.touches,
            "candle_separation": self.candle_separation,
            "price_at_last_bar": self.price_at_last_bar,
            "broken": self.broken,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class Channel:
    direction: str  # "rising" | "falling" | "horizontal"
    base: Trendline
    parallel: tuple[Pivot, Pivot]
    width_atr: float
    opposite_touches: int
    confidence: int
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "base": self.base.to_dict(),
            "parallel": [_pivot_dict(p) for p in self.parallel],
            "width_atr": self.width_atr,
            "opposite_touches": self.opposite_touches,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class PatternInstance:
    pattern_type: PatternType
    status: PatternStatus
    anchors: list[Pivot]
    neckline: tuple[tuple[float, float], tuple[float, float]] | None = None
    projected_target: float | None = None
    break_direction: str | None = None  # "up" | "down"
    #: Bar at which the completing (or invalidating) close happened.
    #:
    #: The reference implementation computed this inside each detector and then
    #: dropped it, which left the ``confirmed`` stage unreachable: the stage
    #: assessment asks for follow-through *after the break bar*, and with no
    #: break bar every completed pattern reported ``completed_unconfirmed``
    #: forever. Carrying it is the whole fix.
    break_index: int | None = None
    #: The price whose breach completes the pattern, when the detector knows a
    #: single such level (a neckline, a boundary at the current bar).
    break_level: float | None = None
    confidence: int = 0
    evidence: list[str] = field(default_factory=list)
    stage: PatternStage | None = None
    completion_ratio: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_type": self.pattern_type.value,
            "status": self.status.value,
            "anchors": [_pivot_dict(p) for p in self.anchors],
            "neckline": self.neckline,
            "projected_target": self.projected_target,
            "break_direction": self.break_direction,
            "break_index": self.break_index,
            "break_level": self.break_level,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "stage": self.stage.value if self.stage else None,
            "completion_ratio": self.completion_ratio,
        }


@dataclass(frozen=True, slots=True)
class CandlestickSignal:
    name: str
    index: int
    ts: str
    direction: str  # "bullish" | "bearish" | "neutral"
    confidence: int
    #: Bars the shape spans; 1 for single-candle shapes.
    span_bars: int = 1
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "index": self.index,
            "ts": self.ts,
            "direction": self.direction,
            "confidence": self.confidence,
            "span_bars": self.span_bars,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class GeometrySnapshot:
    pivots: list[Pivot]
    trendlines: list[Trendline]
    channels: list[Channel]
    patterns: list[PatternInstance]
    candlesticks: list[CandlestickSignal]
    #: The window actually analysed, after the bar cap.
    candle_count: int
    atr: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pivots": [_pivot_dict(p) for p in self.pivots],
            "trendlines": [line.to_dict() for line in self.trendlines],
            "channels": [channel.to_dict() for channel in self.channels],
            "patterns": [pattern.to_dict() for pattern in self.patterns],
            "candlesticks": [signal.to_dict() for signal in self.candlesticks],
            "candle_count": self.candle_count,
            "atr": self.atr,
        }


def _pivot_dict(pivot: Pivot) -> dict[str, Any]:
    return {
        "index": pivot.index,
        "ts": pivot.ts.isoformat(),
        "price": pivot.price,
        "kind": pivot.kind,
    }


def line_price_at_index(a: Pivot, b: Pivot, index: int) -> float:
    """The line through two pivots, evaluated in bar space.

    Bar space rather than time space: candles are evenly spaced by index but
    not by clock once weekends and the daily maintenance break are involved, so
    a line fitted in time would sag across every gap.
    """
    if b.index == a.index:
        return a.price
    t = (index - a.index) / (b.index - a.index)
    return a.price + t * (b.price - a.price)


def clamp_confidence(value: float) -> int:
    return max(0, min(100, js_round(value)))

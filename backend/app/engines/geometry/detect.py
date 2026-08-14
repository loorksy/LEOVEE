"""The geometry engine: one call, bounded deterministic output.

Ported from AiChart's ``detectGeometry.ts``. The same snapshot feeds the
decision path, the rendered chart and the model's numeric context, so a triangle
the model reasons about is the exact triangle drawn on the picture it is shown.

**The bounds are the contract, not a performance measure.** Input is capped at
the last 500 candles; output at two trendlines per side, one channel and three
patterns, everything above a confidence floor. Bounded output is what keeps the
snapshot usable as model context — relax it and the token budget and the drawing
density blow up together, and a chart with forty overlapping claims tells a
reader less than one with three.

**Specificity outranks confidence in the dedup.** A flat-top ascending triangle
also satisfies the looser double-top template, because it does have equal highs.
The converging-boundary claim carries strictly more structure — two fitted
lines, an apex, break rules — so template richness wins the overlap and
confidence only breaks ties.

The reference implementation ranked only head-and-shoulders and the converging
family, leaving cups, rectangles and flags in the same bucket as a double top.
That is not a ranking of structure, it is a ranking of the two families someone
happened to write down: a four-anchor cup with a roundedness test and a handle
rule would lose its own bars to a double bottom scoring two points higher, and a
rectangle — which asserts *both* boundaries — would lose them to a triple bottom
that only asserts one. The table below ranks every template the engine can emit
by what it actually claims, in three tiers.
"""

from __future__ import annotations

from app.core.timeframes import ANALYSIS_WINDOW_BARS, MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.geometry.candlesticks import detect_candlesticks
from app.engines.geometry.channels import detect_channels
from app.engines.geometry.cup_handle import detect_cup_handle
from app.engines.geometry.flags import detect_flags
from app.engines.geometry.pattern_stage import assess_pattern_stage
from app.engines.geometry.rectangles import detect_rectangles
from app.engines.geometry.reversals import (
    detect_double_extremes,
    detect_head_shoulders,
    detect_triple_extremes,
)
from app.engines.geometry.trendlines import detect_trendlines
from app.engines.geometry.triangles import detect_converging_patterns
from app.engines.geometry.types import (
    GeometrySnapshot,
    PatternInstance,
    PatternType,
)
from app.engines.primitives.pivots import all_confirmed_pivots, geometry_atr, zigzag_pivots

__all__ = ["GEOMETRY_MIN_CONFIDENCE", "MAX_PATTERNS", "detect_chart_geometry"]

GEOMETRY_MIN_CONFIDENCE = 60
MAX_PATTERNS = 3

#: How much structure a template asserts. Higher wins an overlap outright.
_SPECIFICITY: dict[PatternType, int] = {
    # Five-anchor asymmetric templates with proportion rules of their own: a
    # head that must clear both shoulders, a base that must be rounded and a
    # handle that must hold the upper half.
    PatternType.HEAD_AND_SHOULDERS: 3,
    PatternType.INVERSE_HEAD_AND_SHOULDERS: 3,
    PatternType.CUP_AND_HANDLE: 3,
    PatternType.INVERSE_CUP_AND_HANDLE: 3,
    # Two-boundary structures: both sides are fitted and both are claimed.
    PatternType.ASCENDING_TRIANGLE: 2,
    PatternType.DESCENDING_TRIANGLE: 2,
    PatternType.SYMMETRICAL_TRIANGLE: 2,
    PatternType.WEDGE: 2,
    PatternType.RECTANGLE: 2,
    PatternType.PENNANT: 2,
    PatternType.FLAG: 2,
    # Single-level templates: a count of defended touches at one price, plus a
    # neckline. The weakest claim that is still a claim, so it yields to any
    # richer description of the same bars.
    PatternType.DOUBLE_TOP: 1,
    PatternType.DOUBLE_BOTTOM: 1,
    PatternType.TRIPLE_TOP: 1,
    PatternType.TRIPLE_BOTTOM: 1,
}


def _empty(candle_count: int, atr: float) -> GeometrySnapshot:
    return GeometrySnapshot(
        pivots=[],
        trendlines=[],
        channels=[],
        patterns=[],
        candlesticks=[],
        candle_count=candle_count,
        atr=atr,
    )


def _span(pattern: PatternInstance) -> tuple[int, int]:
    indexes = [anchor.index for anchor in pattern.anchors]
    return min(indexes), max(indexes)


def _overlaps(a: PatternInstance, b: PatternInstance) -> bool:
    """Two patterns overlap when their bar spans share most of the shorter one."""
    a_from, a_to = _span(a)
    b_from, b_to = _span(b)
    intersection = min(a_to, b_to) - max(a_from, b_from)
    if intersection <= 0:
        return False
    shorter = max(1, min(a_to - a_from, b_to - b_from))
    return intersection / shorter > 0.6


def detect_chart_geometry(
    bars: list[OHLCBar],
    *,
    atr: float | None = None,
    min_confidence: int = GEOMETRY_MIN_CONFIDENCE,
) -> GeometrySnapshot:
    window = bars[-ANALYSIS_WINDOW_BARS:]
    if len(window) < MIN_CANDLES_FOR_ANALYSIS:
        return _empty(len(window), 0.0)

    resolved_atr = atr if atr and atr > 0 else geometry_atr(window)
    if not resolved_atr > 0:
        # No volatility scale means no way to size any threshold, so every
        # detector below would be comparing prices to zero.
        return _empty(len(window), 0.0)

    zigzag = zigzag_pivots(window, resolved_atr)
    # Boundary-fitting detectors want the denser confirmed pivots; template
    # detectors consume the zigzag, which guarantees strict alternation.
    confirmed = all_confirmed_pivots(window)

    trendlines = [
        line
        for line in detect_trendlines(window, confirmed, resolved_atr)
        if line.confidence >= min_confidence
    ]
    channels = [
        channel
        for channel in detect_channels(confirmed, trendlines, resolved_atr)
        if channel.confidence >= min_confidence
    ]

    raw: list[PatternInstance] = [
        *detect_converging_patterns(window, confirmed, resolved_atr),
        *detect_head_shoulders(window, zigzag, resolved_atr),
        *detect_double_extremes(window, zigzag, resolved_atr),
        # Triples run alongside doubles: where three touches exist the triple
        # wins the dedup, because three defended touches score above two.
        *detect_triple_extremes(window, zigzag, resolved_atr),
        *detect_cup_handle(window, zigzag, resolved_atr),
        *detect_rectangles(window, zigzag, resolved_atr),
        # Flags read the bars directly rather than the pivots: the impulse and
        # the pause are both too short to have produced confirmed swings.
        *detect_flags(window, resolved_atr),
    ]
    raw = [pattern for pattern in raw if pattern.confidence >= min_confidence]

    raw.sort(
        key=lambda p: (
            -_SPECIFICITY.get(p.pattern_type, 1),
            -p.confidence,
            p.pattern_type.value,
        )
    )

    kept: list[PatternInstance] = []
    for candidate in raw:
        if len(kept) >= MAX_PATTERNS:
            break
        if all(not _overlaps(existing, candidate) for existing in kept):
            kept.append(candidate)
    kept.sort(key=lambda p: -p.confidence)

    # Stage is assessed after selection so each detector keeps its own break
    # logic untouched, and so a structure nearly finished is recognisable as an
    # opportunity rather than lumped in with one that has barely started.
    staged = [assess_pattern_stage(pattern, window, resolved_atr) for pattern in kept]

    return GeometrySnapshot(
        pivots=zigzag,
        trendlines=trendlines,
        channels=channels,
        patterns=staged,
        candlesticks=detect_candlesticks(window, resolved_atr),
        candle_count=len(window),
        atr=resolved_atr,
    )

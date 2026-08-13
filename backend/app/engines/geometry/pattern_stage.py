"""Where a pattern is in its own life — a second axis, not a finer status.

``PatternStatus`` answers exactly one question: has price closed beyond the
boundary. That is all "forming vs completed" ever meant. But a triangle two
bars old and one pressing its apex are both ``forming``, and they are not
remotely the same trade. Collapsing them is what made "the pattern is not
complete" read as "there is nothing here", when the boundary of a nearly
finished structure is often the best entry available.

So the break state stays exactly as it was and this adds a stage alongside it.
Neither judges the trade: together they describe the structure precisely enough
that the decision engine can weigh an early entry against waiting.

Two inputs feed the stage, and they are deliberately combined rather than
averaged. *Shape progress* is how much of the template exists — three of five
head-and-shoulders anchors is 0.6 of a shape. *Proximity* is how close price
sits to the level that would complete it. A complete template still two ATR
from its neckline is mid-formation; a partial one pressing the level is nearly
there. Taking the larger of the two (discounted) lets either route to
``near_completion`` without letting a weak signal on one axis drag down a
strong one on the other.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from app.engines.bar import OHLCBar
from app.engines.geometry.types import PatternInstance, PatternStage, PatternStatus

__all__ = [
    "CONFIRMATION_ATR",
    "StageAssessment",
    "assess_pattern_stage",
    "expected_anchors_for",
    "break_level_of",
    "offers_anticipatory_entry",
]

#: Follow-through beyond the break needed before a completion is "confirmed".
#: Half an ATR: less than that and the "break" is inside the bar-to-bar noise
#: that produced it, which is the shape of every failed breakout.
CONFIRMATION_ATR = 0.5

_STARTING_BELOW = 0.35
_FORMING_BELOW = 0.75
#: Two ATR from the completing level scores zero proximity; at the level, one.
_PROXIMITY_SPAN_ATR = 2.0


@dataclass(frozen=True, slots=True)
class StageAssessment:
    stage: PatternStage
    #: 0-1: how much of the structure's expected shape has actually formed.
    completion_ratio: float


def expected_anchors_for(pattern_type: str) -> int:
    """Anchors a complete template of each pattern family has."""
    if "head_and_shoulders" in pattern_type:
        return 5
    if "triple" in pattern_type:
        return 5
    if "cup" in pattern_type:
        return 4
    if pattern_type == "rectangle":
        return 4
    if "double" in pattern_type:
        return 4
    if "triangle" in pattern_type or "wedge" in pattern_type:
        return 4
    if "flag" in pattern_type or "pennant" in pattern_type:
        return 3
    return 3


def break_level_of(pattern: PatternInstance) -> float | None:
    """The price whose breach would complete this pattern, if there is one.

    Detectors that fit boundaries record it directly; reversal templates carry
    it on the neckline. Where neither exists the assessment falls back to shape
    progress alone rather than inventing a level.
    """
    if pattern.break_level is not None and isfinite(pattern.break_level):
        return pattern.break_level
    if pattern.neckline is not None:
        return pattern.neckline[1][1]
    return None


def _proximity_progress(last_close: float, break_level: float | None, atr: float) -> float | None:
    if break_level is None or not isfinite(break_level):
        return None
    if not atr > 0:
        return None
    distance_atr = abs(last_close - break_level) / atr
    return max(0.0, min(1.0, 1 - distance_atr / _PROXIMITY_SPAN_ATR))


def _assess(
    *,
    status: PatternStatus,
    anchor_count: int,
    expected_anchors: int,
    bars: list[OHLCBar],
    break_index: int | None,
    break_level: float | None,
    atr: float,
) -> StageAssessment:
    shape_progress = (
        max(0.0, min(1.0, anchor_count / expected_anchors)) if expected_anchors > 0 else 0.0
    )

    if status is PatternStatus.INVALIDATED:
        return StageAssessment(stage=PatternStage.FAILED, completion_ratio=shape_progress)

    if status is PatternStatus.COMPLETED:
        confirmed = (
            break_index is not None
            and break_level is not None
            and atr > 0
            and any(
                abs(candle.close - break_level) > atr * CONFIRMATION_ATR
                for candle in bars[break_index + 1 :]
            )
        )
        return StageAssessment(
            stage=PatternStage.CONFIRMED if confirmed else PatternStage.COMPLETED_UNCONFIRMED,
            completion_ratio=1.0,
        )

    last_close = bars[-1].close if bars else None
    proximity = None if last_close is None else _proximity_progress(last_close, break_level, atr)
    ratio = shape_progress if proximity is None else max(shape_progress * 0.6, proximity * 0.9)

    if ratio < _STARTING_BELOW:
        return StageAssessment(stage=PatternStage.STARTING, completion_ratio=ratio)
    if ratio < _FORMING_BELOW:
        return StageAssessment(stage=PatternStage.FORMING, completion_ratio=ratio)
    return StageAssessment(stage=PatternStage.NEAR_COMPLETION, completion_ratio=ratio)


def assess_pattern_stage(
    pattern: PatternInstance, bars: list[OHLCBar], atr: float
) -> PatternInstance:
    """Return the pattern with its stage and completion ratio filled in."""
    assessment = _assess(
        status=pattern.status,
        anchor_count=len(pattern.anchors),
        expected_anchors=expected_anchors_for(pattern.pattern_type.value),
        bars=bars,
        break_index=pattern.break_index,
        break_level=break_level_of(pattern),
        atr=atr,
    )
    return replace(
        pattern,
        stage=assessment.stage,
        # Two places round the same number to two decimals so the snapshot is
        # byte-stable across runs; the raw float is not evidence of anything at
        # the third decimal.
        completion_ratio=round(assessment.completion_ratio, 2),
    )


def offers_anticipatory_entry(stage: PatternStage) -> bool:
    """Is this stage an opportunity to enter BEFORE confirmation?"""
    return stage in (PatternStage.FORMING, PatternStage.NEAR_COMPLETION)

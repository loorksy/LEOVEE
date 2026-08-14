"""Which frame carries the setup — chosen by the agent, never by the user.

This replaces ``INTERIM_DECISION_TIMEFRAME``, which held the pipeline together
while the selection logic was still to be written and was named as a stand-in
rather than dressed up as a decision.

**Deterministic, not a model call.** Timeframe choice is the one judgement in
the pipeline with a clean numeric answer: pick the scalping frame where the
structure is most legible and the volatility is workable. Handing it to a model
buys nothing and costs reproducibility — two runs on the same candles would
choose differently and neither could be explained.

The score has three terms, and the *ordering* between them matters more than
the weights:

**Legibility dominates.** A frame with no readable structure cannot carry a
plan whatever else it has going for it, so an unreadable frame is excluded
outright rather than penalised.

**Agreement with the leading context frame is a bonus, not a filter.** A frame
that disagrees with H4 can still be the right one to trade — that is what a
counter-trend scalp is — but it has to earn it.

**Room to trade is a score, not an exclusion, and it is measured.** How far a
frame's stop clears the movement price routinely gives back within a candle is
real information about that frame, so it ranks — but it does not disqualify.

It used to disqualify, against a *modelled* retail spread, and that was wrong in
a way worth naming: an invented constant excluded one-minute gold on every
ordinary tape, and the platform refused a whole timeframe because of a number
nobody had measured. Only two things exclude a frame now, and both are facts
about the candles: there are not enough of them, or they carry no readable
structure.

When every frame is excluded the selector says so instead of falling back to a
default. A default here is a confident answer about the wrong chart.

**Nothing here reads the clock.** An earlier version did, indirectly: the cost
floor was session-shaped, so identical candles chose different frames depending
on when the run happened, and a replay could not reproduce it. Measuring the
floor from the candles removes the clock from the decision entirely — the same
bars now always give the same answer, whenever they are read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.timeframes import DECISION_TIMEFRAMES, MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.plan_sanity import measure_price_context, risk_policy_for
from app.engines.primitives.pivots import geometry_atr
from app.engines.primitives.regime import detect_market_regime
from app.engines.primitives.structure import detect_structure_levels
from app.models.enums import Timeframe

__all__ = [
    "TimeframeChoice",
    "TimeframeCandidate",
    "select_decision_timeframe",
    "NoViableTimeframeError",
]

#: A trending regime makes structure worth acting on; a blowout makes any read
#: fragile. Applied after legibility, never instead of it.
_REGIME_BONUS = {"trending": 20.0, "ranging": 8.0, "high_volatility": 0.0, "low_liquidity": 0.0}

_SHAPE_SCORE = {"uptrend": 30.0, "downtrend": 30.0, "range": 12.0, "unknown": 0.0}

#: Agreement with the frame that leads the context stack.
_ALIGNED_BONUS = 15.0
_CONFLICT_PENALTY = 10.0

#: Swings per frame, capped: more structure is better up to a point, past which
#: it is noise being counted as evidence.
_MAX_SWING_CREDIT = 12.0


class NoViableTimeframeError(RuntimeError):
    """No scalping frame can carry a plan right now.

    Raised rather than returning a default: a default here is a confident answer
    about a chart the agent has just established it cannot read.
    """


@dataclass(frozen=True, slots=True)
class TimeframeCandidate:
    timeframe: Timeframe
    score: float
    atr: float
    shape: str
    regime: str | None
    bars: int
    #: Why it was excluded, if it was. Empty means it competed.
    excluded: str | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe.value,
            "score": round(self.score, 2),
            "atr": round(self.atr, 5),
            "shape": self.shape,
            "regime": self.regime,
            "bars": self.bars,
            "excluded": self.excluded,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class TimeframeChoice:
    timeframe: Timeframe
    rationale: str
    candidates: list[TimeframeCandidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe.value,
            "rationale": self.rationale,
            "candidates": [c.to_dict() for c in self.candidates],
        }


def _assess(
    timeframe: Timeframe,
    bars: list[OHLCBar],
    *,
    leading_bias: str | None,
) -> TimeframeCandidate:
    if len(bars) < MIN_CANDLES_FOR_ANALYSIS:
        return TimeframeCandidate(
            timeframe=timeframe,
            score=0.0,
            atr=0.0,
            shape="unknown",
            regime=None,
            bars=len(bars),
            excluded="INSUFFICIENT_BARS",
        )

    atr = geometry_atr(bars)
    structure = detect_structure_levels(bars)
    regime = detect_market_regime(bars)
    reasons: list[str] = []

    if structure.structure == "unknown":
        # Not a low score — an exclusion. A frame with no readable structure
        # cannot carry a plan however attractive its volatility looks.
        return TimeframeCandidate(
            timeframe=timeframe,
            score=0.0,
            atr=atr,
            shape=structure.structure,
            regime=regime.regime if regime.is_known else None,
            bars=len(bars),
            excluded="NO_READABLE_STRUCTURE",
        )

    # How much room a stop on this frame has above the movement price gives back
    # inside a candle. Real information, so it ranks — but a frame is never
    # excluded for it, because that judgement belongs to the plan, not the
    # timeframe, and the plan is checked directly.
    policy = risk_policy_for(timeframe)
    context = measure_price_context(bars, atr=atr)
    stop_distance = atr * policy.stop_atr_multiple
    headroom = stop_distance / context.noise if context.noise > 0 else 0.0

    score = _SHAPE_SCORE[structure.structure]
    reasons.append(f"structure={structure.structure}")

    swings = min(_MAX_SWING_CREDIT, float(len(structure.swing_highs) + len(structure.swing_lows)))
    score += swings
    reasons.append(f"swings={int(swings)}")

    if regime.is_known:
        score += _REGIME_BONUS.get(regime.regime, 0.0)
        reasons.append(f"regime={regime.regime}")

    bias = {"uptrend": "BULLISH", "downtrend": "BEARISH"}.get(structure.structure)
    if leading_bias in ("BULLISH", "BEARISH") and bias is not None:
        if bias == leading_bias:
            score += _ALIGNED_BONUS
            reasons.append("aligned with context")
        else:
            # A penalty, not an exclusion: trading against the higher frame is a
            # real setup, it just has to be worth more than the frames that agree.
            score -= _CONFLICT_PENALTY
            reasons.append("against context")

    # Capped: a frame whose stop is twenty times its wick noise is not
    # proportionally better, it is just slower.
    score += min(10.0, max(0.0, headroom - 1) * 3)
    reasons.append(f"stop={headroom:.1f}x wick noise")

    return TimeframeCandidate(
        timeframe=timeframe,
        score=score,
        atr=atr,
        shape=structure.structure,
        regime=regime.regime if regime.is_known else None,
        bars=len(bars),
        reasons=reasons,
    )


def select_decision_timeframe(
    bars_by_timeframe: dict[str, list[OHLCBar]],
    *,
    leading_bias: str | None = None,
) -> TimeframeChoice:
    """Pick the scalping frame that can actually carry a plan on this tape.

    Deterministic in the strongest sense: the same bars always give the same
    answer, with no clock, no session table and no assumption about anyone's
    execution costs entering the decision.
    """
    candidates = [
        _assess(
            tf,
            bars_by_timeframe.get(tf.value) or [],
            leading_bias=leading_bias,
        )
        for tf in DECISION_TIMEFRAMES
    ]
    viable = [c for c in candidates if c.excluded is None]
    if not viable:
        raise NoViableTimeframeError(
            "no scalping frame can carry a plan: "
            + ", ".join(f"{c.timeframe.value}={c.excluded}" for c in candidates)
        )

    # Ties break on the slower frame: given equal evidence, the slower frame has
    # more of it per bar and its levels survive longer.
    best = max(viable, key=lambda c: (c.score, DECISION_TIMEFRAMES.index(c.timeframe)))
    return TimeframeChoice(
        timeframe=best.timeframe,
        rationale="; ".join(best.reasons),
        candidates=candidates,
    )

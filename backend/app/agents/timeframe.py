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

**Room to trade is a hard floor.** If the frame's own volatility cannot produce
a first target clearing the round-trip cost, no plan on it can ever be viable,
so it is excluded for the same reason as an unreadable frame: not "worse", but
*impossible*.

When every frame is excluded the selector says so instead of falling back to a
default. A default here is a confident answer about the wrong chart.

**The moment is an input, not the wall clock.** Spread is session-shaped, so the
cost floor moves between Asia and the London/New York overlap — and a selector
that read ``now()`` would return different frames for identical candles
depending on when it ran, with nothing in the output explaining why. Replaying
an analysis would not reproduce it either. The caller passes the moment the
candles belong to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.timeframes import DECISION_TIMEFRAMES, MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.plan_sanity import (
    MIN_COST_MULTIPLE,
    estimate_spread_pips,
    risk_policy_for,
    round_trip_cost_pips,
)
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
    symbol: str,
    moment: datetime | None,
    observed_spread_pips: float | None,
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

    # Room to trade: does this frame's own volatility reach past the costs?
    policy = risk_policy_for(timeframe)
    spread = estimate_spread_pips(symbol=symbol, observed_pips=observed_spread_pips, moment=moment)
    required_pips = round_trip_cost_pips(spread.pips) * MIN_COST_MULTIPLE
    pip = spread.price / spread.pips if spread.pips else 0.01
    first_target_pips = (atr * policy.stop_atr_multiple * policy.target_r[0]) / pip
    if first_target_pips < required_pips:
        return TimeframeCandidate(
            timeframe=timeframe,
            score=0.0,
            atr=atr,
            shape=structure.structure,
            regime=regime.regime if regime.is_known else None,
            bars=len(bars),
            excluded="NO_ROOM_AFTER_COSTS",
            reasons=[f"first target ~{first_target_pips:.0f} pips vs {required_pips:.0f} required"],
        )

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

    # Headroom past the cost floor, capped: a frame with enormous range is not
    # proportionally better, it is just noisier.
    score += min(10.0, (first_target_pips / required_pips - 1) * 5)

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
    symbol: str = "XAUUSD",
    moment: datetime | None = None,
    observed_spread_pips: float | None = None,
) -> TimeframeChoice:
    """Pick the scalping frame that can actually carry a plan at this moment.

    `moment` shapes the spread and therefore the cost floor. Passing the last
    candle's timestamp — rather than letting it default to the clock — is what
    keeps the choice reproducible and replayable.
    """
    candidates = [
        _assess(
            tf,
            bars_by_timeframe.get(tf.value) or [],
            leading_bias=leading_bias,
            symbol=symbol,
            moment=moment,
            observed_spread_pips=observed_spread_pips,
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

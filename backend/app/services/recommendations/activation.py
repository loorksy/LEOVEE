"""When does a conditional plan become live?

A conditional recommendation is a BUY or SELL whose entry condition has not been
met (ADR 0002). This is the machinery that decides whether it has.

**The rule is data, not prose.** "Wait for a break of 2005" is a sentence a
person reads; ``candle_close_above(level=2005, closes=1)`` is something a worker
evaluates every minute without asking anyone. Storing the sentence and hoping
someone reads it is how a conditional plan sits at *awaiting activation* through
the entire move it was waiting for.

**Seven kinds, and the distinctions between them are the point.** A touch, a
close beyond, a confirmed break, a retest, a rejection — these describe
different things that a single "price reached X" would flatten into one. The
difference between a wick through a level and a close beyond it is the
difference between a sweep and a break, and a plan that cannot express which one
it is waiting for is waiting for the wrong thing half the time.

**A rule that is already true is a rule that was never a condition.** Writing
"wait for a close above 2005" when price is already at 2010 produces a plan that
activates on the next bar regardless of what happens, which is an immediate plan
wearing a condition. The coherence check rejects those rather than letting them
through as instantly-satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engines.bar import OHLCBar

__all__ = [
    "ActivationKind",
    "ActivationRule",
    "LeafRule",
    "CompositeRule",
    "ActivationOutcome",
    "evaluate_activation",
    "explain_incoherence",
    "MAX_COMPOSITE_RULES",
    "MAX_CONSECUTIVE_CLOSES",
]

#: One level deep. A composite of composites is a boolean expression tree, and
#: nothing a trader says out loud needs one — while everything that reads a rule
#: would need to handle arbitrary nesting.
MAX_COMPOSITE_RULES = 4
MIN_COMPOSITE_RULES = 2
MAX_CONSECUTIVE_CLOSES = 10


class ActivationKind(StrEnum):
    #: Price simply reached the level. Satisfied by a wick.
    PRICE_TOUCH = "price_touch"
    #: N consecutive closes above. A wick through does not count.
    CANDLE_CLOSE_ABOVE = "candle_close_above"
    CANDLE_CLOSE_BELOW = "candle_close_below"
    #: A directional close beyond the level — the same test as the two above,
    #: but the direction travels with the rule instead of the kind, so a
    #: direction/plan mismatch is checkable.
    BREAKOUT_CONFIRMED = "breakout_confirmed"
    #: Broke, came back into a zone, and left it again the same way. The
    #: patient version: it trades the second chance rather than the first.
    RETEST_CONFIRMED = "retest_confirmed"
    #: Reached beyond the level and closed back. A sweep, named as one.
    REJECTION_CONFIRMED = "rejection_confirmed"
    COMPOSITE = "composite"


Level = Annotated[float, Field(gt=0)]
Tolerance = Annotated[float, Field(ge=0)]
Closes = Annotated[int, Field(ge=1, le=MAX_CONSECUTIVE_CLOSES)]


class _Rule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Which frame the closes are counted on. Filled from the analysis when the
    #: model omits it — "three closes" means nothing without a bar size.
    timeframe: str | None = None
    #: Epoch seconds. A condition with no expiry waits forever, and a plan
    #: waiting on a level price left behind two sessions ago is noise.
    expires_at: float | None = None


class PriceTouchRule(_Rule):
    kind: Literal[ActivationKind.PRICE_TOUCH] = ActivationKind.PRICE_TOUCH
    level: Level
    #: Which side price must approach from. None accepts either.
    direction: Literal["above", "below"] | None = None
    tolerance: Tolerance = 0.0


class CandleCloseRule(_Rule):
    kind: Literal[ActivationKind.CANDLE_CLOSE_ABOVE, ActivationKind.CANDLE_CLOSE_BELOW]
    level: Level
    tolerance: Tolerance = 0.0
    closes: Closes = 1


class BreakoutRule(_Rule):
    kind: Literal[ActivationKind.BREAKOUT_CONFIRMED] = ActivationKind.BREAKOUT_CONFIRMED
    level: Level
    direction: Literal["above", "below"]
    tolerance: Tolerance = 0.0
    closes: Closes = 1


class RetestZone(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: float
    high: float

    @model_validator(mode="after")
    def ordered(self) -> RetestZone:
        if self.high < self.low:
            raise ValueError("retest zone high must be at or above low")
        return self


class RetestRule(_Rule):
    kind: Literal[ActivationKind.RETEST_CONFIRMED] = ActivationKind.RETEST_CONFIRMED
    level: Level
    direction: Literal["above", "below"]
    retest_zone: RetestZone
    tolerance: Tolerance = 0.0
    closes: Closes = 1


class RejectionRule(_Rule):
    kind: Literal[ActivationKind.REJECTION_CONFIRMED] = ActivationKind.REJECTION_CONFIRMED
    level: Level
    #: The side price must close back *towards*. For a long waiting on support
    #: to hold, that is "above".
    direction: Literal["above", "below"]
    tolerance: Tolerance = 0.0


LeafRule = Annotated[
    PriceTouchRule | CandleCloseRule | BreakoutRule | RetestRule | RejectionRule,
    Field(discriminator="kind"),
]


class CompositeRule(_Rule):
    kind: Literal[ActivationKind.COMPOSITE] = ActivationKind.COMPOSITE
    operator: Literal["all", "any"]
    rules: list[LeafRule] = Field(min_length=MIN_COMPOSITE_RULES, max_length=MAX_COMPOSITE_RULES)


ActivationRule = Annotated[
    PriceTouchRule | CandleCloseRule | BreakoutRule | RetestRule | RejectionRule | CompositeRule,
    Field(discriminator="kind"),
]


@dataclass(frozen=True, slots=True)
class ActivationOutcome:
    satisfied: bool
    #: The bar that satisfied it, so the activation can be dated rather than
    #: just observed. A plan that activated four bars ago and a plan that
    #: activated on this tick call for different things.
    at_index: int | None = None
    #: Human-readable, for the trace and the card.
    detail: str = ""

    @property
    def pending(self) -> bool:
        return not self.satisfied


def _leaves(rule: Any) -> list[Any]:
    return list(rule.rules) if isinstance(rule, CompositeRule) else [rule]


def _touched(bar: OHLCBar, level: float, tolerance: float, direction: str | None) -> bool:
    if direction == "above":
        # Approached from above: the bar must reach down to the level.
        return bar.low <= level + tolerance
    if direction == "below":
        return bar.high >= level - tolerance
    return bar.low <= level + tolerance and bar.high >= level - tolerance


def _consecutive_closes(
    bars: list[OHLCBar], level: float, tolerance: float, side: str, closes: int, start: int = 0
) -> int | None:
    """Index of the bar completing `closes` consecutive closes beyond `level`.

    Consecutive, not cumulative. Three closes above a level with a close back
    below in between is not confirmation of anything — it is a level being
    fought over, and counting them together would report a break that price
    spent the whole window rejecting.
    """
    run = 0
    for index in range(max(0, start), len(bars)):
        close = bars[index].close
        beyond = close > level + tolerance if side == "above" else close < level - tolerance
        run = run + 1 if beyond else 0
        if run >= closes:
            return index
    return None


def _evaluate_leaf(rule: Any, bars: list[OHLCBar]) -> ActivationOutcome:
    if isinstance(rule, PriceTouchRule):
        for index, bar in enumerate(bars):
            if _touched(bar, rule.level, rule.tolerance, rule.direction):
                return ActivationOutcome(True, index, f"touched {rule.level:g}")
        return ActivationOutcome(False, detail=f"has not reached {rule.level:g}")

    if isinstance(rule, CandleCloseRule):
        side = "above" if rule.kind is ActivationKind.CANDLE_CLOSE_ABOVE else "below"
        closed_at = _consecutive_closes(bars, rule.level, rule.tolerance, side, rule.closes)
        if closed_at is not None:
            return ActivationOutcome(
                True, closed_at, f"{rule.closes} close(s) {side} {rule.level:g}"
            )
        return ActivationOutcome(False, detail=f"no {rule.closes} close(s) {side} {rule.level:g}")

    if isinstance(rule, BreakoutRule):
        broke_at = _consecutive_closes(
            bars, rule.level, rule.tolerance, rule.direction, rule.closes
        )
        if broke_at is not None:
            return ActivationOutcome(True, broke_at, f"broke {rule.direction} {rule.level:g}")
        return ActivationOutcome(False, detail=f"no break {rule.direction} {rule.level:g}")

    if isinstance(rule, RetestRule):
        # Three phases in order, and the order is the rule. A retest that
        # happened before the break is not a retest, it is the approach.
        broke = _consecutive_closes(bars, rule.level, rule.tolerance, rule.direction, rule.closes)
        if broke is None:
            return ActivationOutcome(False, detail=f"no break {rule.direction} {rule.level:g} yet")
        zone = rule.retest_zone
        returned = next(
            (
                i
                for i in range(broke + 1, len(bars))
                if bars[i].low <= zone.high and bars[i].high >= zone.low
            ),
            None,
        )
        if returned is None:
            return ActivationOutcome(False, detail="broke, awaiting the retest")
        left = _consecutive_closes(
            bars, rule.level, rule.tolerance, rule.direction, rule.closes, start=returned + 1
        )
        if left is None:
            return ActivationOutcome(False, detail="in the retest zone, not yet resumed")
        return ActivationOutcome(True, left, f"retested and resumed {rule.direction}")

    if isinstance(rule, RejectionRule):
        for index, bar in enumerate(bars):
            # Reached through and closed back: a wick beyond, a body on the
            # origin side. Both halves are required — a close beyond is a break,
            # and a bar that never reached the level rejected nothing.
            if rule.direction == "above":
                pierced = bar.low <= rule.level - rule.tolerance
                closed_back = bar.close > rule.level + rule.tolerance
            else:
                pierced = bar.high >= rule.level + rule.tolerance
                closed_back = bar.close < rule.level - rule.tolerance
            if pierced and closed_back:
                return ActivationOutcome(True, index, f"rejected {rule.level:g}")
        return ActivationOutcome(False, detail=f"no rejection at {rule.level:g}")

    raise TypeError(f"unknown activation rule: {type(rule).__name__}")


def evaluate_activation(rule: Any, bars: list[OHLCBar]) -> ActivationOutcome:
    """Has this condition been met over these bars?"""
    if not bars:
        return ActivationOutcome(False, detail="no bars to evaluate")

    if isinstance(rule, CompositeRule):
        outcomes = [_evaluate_leaf(leaf, bars) for leaf in rule.rules]
        met = [o for o in outcomes if o.satisfied]
        if rule.operator == "all":
            if len(met) != len(outcomes):
                missing = "; ".join(o.detail for o in outcomes if not o.satisfied)
                return ActivationOutcome(False, detail=missing)
            # The last one to be met is when the whole rule became true.
            indexes = [o.at_index for o in met if o.at_index is not None]
            return ActivationOutcome(
                True, max(indexes) if indexes else None, "; ".join(o.detail for o in met)
            )
        if not met:
            return ActivationOutcome(False, detail="; ".join(o.detail for o in outcomes))
        indexes = [o.at_index for o in met if o.at_index is not None]
        return ActivationOutcome(True, min(indexes) if indexes else None, met[0].detail)

    return _evaluate_leaf(rule, bars)


def explain_incoherence(
    rule: Any, *, direction: str, current_price: float, tolerance: float = 0.0
) -> str | None:
    """Why this condition can never mean what the plan intends, or None.

    Two failures, both of which produce a plan that looks patient and is not:

    **Already satisfied.** A condition the current price already meets activates
    on the next bar whatever happens. That is an immediate plan wearing a
    condition, and the reader waits for a trigger that already fired.

    **Contradicts the direction.** A long waiting for a rejection *below* a
    level is waiting for the level to fail, which is the case that kills the
    trade. Permanently unsatisfiable in the useful sense.
    """
    wanted = "above" if direction.upper() == "BUY" else "below"

    for leaf in _leaves(rule):
        level = getattr(leaf, "level", None)
        if level is None:
            continue

        if isinstance(leaf, RejectionRule) and leaf.direction != wanted:
            return (
                f"a {direction} cannot wait on a rejection closing {leaf.direction} "
                f"{level:g} — that is the case that invalidates it"
            )

        if isinstance(leaf, BreakoutRule) and leaf.direction != wanted:
            return f"a {direction} cannot activate on a break {leaf.direction} {level:g}"

        if isinstance(leaf, CandleCloseRule):
            side = "above" if leaf.kind is ActivationKind.CANDLE_CLOSE_ABOVE else "below"
            already = (
                current_price > level + leaf.tolerance + tolerance
                if side == "above"
                else current_price < level - leaf.tolerance - tolerance
            )
            if already:
                return (
                    f"price is already {side} {level:g}, so this condition is "
                    "already met and the plan is not conditional"
                )

        if isinstance(leaf, BreakoutRule):
            already = (
                current_price > level + leaf.tolerance + tolerance
                if leaf.direction == "above"
                else current_price < level - leaf.tolerance - tolerance
            )
            if already:
                return f"price is already beyond {level:g}; the break has happened"

    # A touch is instantaneous by design and can never be "already satisfied" in
    # a way that misleads: if price is there, the plan is live now, which is
    # what a touch condition means.
    return None

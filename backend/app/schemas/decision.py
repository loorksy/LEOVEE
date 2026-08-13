"""The decision contract: what a completed analysis is allowed to say.

This is where ADR 0002 stops being a document and becomes a type.

**Every successful analysis carries a direction.** BUY or SELL — there is no
third analytical opinion. "The market could go either way" is not a read; it is
the absence of one, and publishing it as a result trains the reader to ignore
the product.

**NO_TRADE is an operational failure, not an opinion.** It means the analysis
could not be completed — an engine declined, the data was stale, the model layer
was unreachable — and it therefore *must* name which. The model enforces this in
both directions: a NO_TRADE without a reason will not validate, and a BUY/SELL
carrying a degraded reason will not either. Those two rules are what stop the
fail-closed path and the analytical path from blurring into each other, which is
exactly how a soft "we're not sure" ends up sitting where a recommendation
should be.

Three axes travel separately and are never collapsed:

- **the opinion** — BUY or SELL;
- **the plan type** — immediate, anticipatory or conditional;
- **the execution state** — valid now, awaiting activation, expired, invalidated.

A conditional plan that has not triggered is not a weak BUY. It is a BUY whose
entry condition has not been met, and flattening that into a confidence number
loses the only thing the reader needed to know.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import RecommendationDirection

__all__ = [
    "PlanType",
    "ExecutionState",
    "DegradedReason",
    "PlanLevels",
    "DecisionOutput",
    "ANALYTICAL_DIRECTIONS",
]

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]

#: The only two directions an analysis may conclude with. WAIT and NO_TRADE are
#: not opinions and are unreachable from the analytical path.
ANALYTICAL_DIRECTIONS = frozenset({RecommendationDirection.BUY, RecommendationDirection.SELL})


class PlanType(StrEnum):
    #: Valid at the current price, right now.
    IMMEDIATE = "IMMEDIATE"
    #: Positioned ahead of a level price has not reached yet.
    ANTICIPATORY = "ANTICIPATORY"
    #: Waits on a named condition — a break, a retest, a session open.
    CONDITIONAL = "CONDITIONAL"


class ExecutionState(StrEnum):
    VALID_NOW = "VALID_NOW"
    AWAITING_ACTIVATION = "AWAITING_ACTIVATION"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class DegradedReason(StrEnum):
    """Why an analysis could not be completed. Never a market condition."""

    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_BAD_REQUEST = "LLM_BAD_REQUEST"
    #: The model answered, and what it said would not validate.
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    MODEL_PLAN_INVALID = "MODEL_PLAN_INVALID"
    #: A price in the plan corresponds to nothing the engines measured.
    LEVELS_NOT_GROUNDED = "LEVELS_NOT_GROUNDED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_CANDLES = "NO_CANDLES"
    NO_VIABLE_TIMEFRAME = "NO_VIABLE_TIMEFRAME"
    PROMPT_UNAVAILABLE = "PROMPT_UNAVAILABLE"
    STALE_DATA = "STALE_DATA"
    MARKET_CLOSED = "MARKET_CLOSED"
    PLAN_NOT_VIABLE = "PLAN_NOT_VIABLE"


class PlanLevels(BaseModel):
    """The prices. Ordering is checked here so no consumer has to."""

    model_config = ConfigDict(frozen=True)

    entry: float
    stop: float
    targets: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def levels_must_sit_on_the_right_sides(self) -> Self:
        if self.entry == self.stop:
            raise ValueError("entry and stop cannot be the same price")
        long_side = self.stop < self.entry
        for target in self.targets:
            # A target on the stop's side of entry is not an ambitious plan, it
            # is a sign convention error — and it produces a negative reward:risk
            # that reads as a very confident bad trade.
            if long_side and target <= self.entry:
                raise ValueError("a long plan's targets must sit above entry")
            if not long_side and target >= self.entry:
                raise ValueError("a short plan's targets must sit below entry")
        return self


class DecisionOutput(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    direction: RecommendationDirection
    confidence: Confidence | None = None
    rationale: str | None = None
    plan_type: PlanType | None = None
    execution_state: ExecutionState | None = None
    levels: PlanLevels | None = None
    timeframe: str | None = None
    degraded: bool = False
    degraded_reason: DegradedReason | None = None
    detail: str | None = None
    #: What must happen before a conditional plan is live. Required for one —
    #: see the validator.
    condition: str | None = None
    #: How many candles the plan stays meaningful for. A plan with no lifetime
    #: is a plan that is still "valid" three sessions after the structure that
    #: justified it stopped existing.
    validity_candles: int | None = Field(default=None, ge=1, le=96)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def no_trade_and_a_direction_are_mutually_exclusive_worlds(self) -> Self:
        if self.direction is RecommendationDirection.WAIT:
            raise ValueError(
                "WAIT is not an analytical outcome (ADR 0002); use NO_TRADE with "
                "a degraded_reason for an operational failure"
            )

        if self.direction is RecommendationDirection.NO_TRADE:
            if not self.degraded or self.degraded_reason is None:
                raise ValueError(
                    "NO_TRADE is an operational failure and must name its reason; "
                    "an analysis that completed produces BUY or SELL (ADR 0002)"
                )
            if self.confidence is not None:
                # A confidence figure on a failure invites the reader to treat
                # it as a weak opinion, which is precisely what it is not.
                raise ValueError("a failed analysis has no confidence to report")
            return self

        if self.degraded or self.degraded_reason is not None:
            raise ValueError(
                "a degraded run cannot also carry a direction; fail closed to "
                "NO_TRADE instead of publishing a softened BUY/SELL"
            )
        if self.confidence is None:
            raise ValueError("a completed analysis must report its confidence")
        if self.levels is None:
            raise ValueError("a completed analysis must carry a full plan")
        if self.plan_type is None or self.execution_state is None:
            raise ValueError("plan type and execution state travel with every direction")
        if self.plan_type is PlanType.CONDITIONAL and not (self.condition or "").strip():
            # A conditional plan whose condition is not stated is unactionable:
            # the reader is told to wait without being told for what, which is
            # strictly worse than an immediate plan they can judge.
            raise ValueError("a conditional plan must state the condition it waits on")
        return self

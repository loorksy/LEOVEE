"""Watching open plans, so a condition that fires is noticed.

Without this the lifecycle is a story the analysis tells once. A conditional
plan sits at *awaiting activation* through the entire move it was waiting for; a
plan whose invalidation level broke keeps its READY badge; an idea from three
sessions ago still reads as live. Every one of those is the product being
confidently wrong in the user's favour, which is the direction that costs money.

**Four questions per plan, in this order**, and the order encodes which fact
dominates:

1. **Has it been invalidated?** Checked first, because a plan whose stop broke
   is finished regardless of what else happened afterwards — including hitting
   its target on the bounce.
2. **Has it reached target?**
3. **Has its condition fired?** Only then is a conditional plan live.
4. **Has it expired?** Last, because an expiry is what is left when nothing
   else happened.

**A plan is evaluated against the bars since it was written**, not against the
latest price alone. A stop that was hit and recovered from is still a stop that
was hit — reading only the current price reports a trade that is winning when it
was closed out two bars ago.

**A terminal transition feeds the learning loop.** Setting the status directly
would move the row and record the revision while leaving M8 blind to the
outcome — and the outcomes the tracker produces are precisely the ones nobody
reported by hand, which is to say the unflattering half of the sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.engines.bar import OHLCBar
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.recommendation import Recommendation
from app.schemas.decision import ExecutionState
from app.services.learning.terminal_hooks import on_recommendation_terminal_status
from app.services.recommendation_lifecycle import (
    TERMINAL_RECOMMENDATION_STATUSES,
    assert_recommendation_transition,
)
from app.services.recommendations.activation import ActivationRule, evaluate_activation
from app.services.recommendations.revisions import (
    RevisionReason,
    lock_recommendation,
    record_revision,
)

logger = structlog.get_logger(__name__)

__all__ = ["TrackerOutcome", "evaluate_recommendation", "parse_activation_rule"]

_RULE_ADAPTER: TypeAdapter[Any] = TypeAdapter(ActivationRule)


@dataclass(frozen=True, slots=True)
class TrackerOutcome:
    changed: bool
    status: RecommendationStatus
    reason: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "status": self.status.value,
            "reason": self.reason,
            "detail": self.detail,
        }


def parse_activation_rule(payload: dict[str, Any] | None) -> Any | None:
    """Rebuild a stored rule, or None if it cannot be read.

    A rule written by an older release may no longer validate. Returning None
    leaves the plan pending rather than crashing the tracker for every *other*
    plan in the workspace — one unreadable row must not stop the loop.
    """
    if not payload:
        return None
    try:
        return _RULE_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        logger.warning("activation_rule_unreadable", error=str(exc)[:200])
        return None


def _hit(bars: list[OHLCBar], level: float, direction: str) -> int | None:
    """First bar whose range contains the level, coming from `direction`.

    Intrabar, not on closes: a stop is an order resting in the book, and price
    trading through it fills it whether or not the candle closes there. Using
    closes here would report a trade still open that was closed on the wick.
    """
    for index, bar in enumerate(bars):
        if direction == "above" and bar.high >= level:
            return index
        if direction == "below" and bar.low <= level:
            return index
    return None


def _invalidated_at(
    recommendation: Recommendation, bars: list[OHLCBar]
) -> tuple[int | None, float | None]:
    if recommendation.stop is None:
        return None, None
    stop = float(recommendation.stop)
    side = "below" if recommendation.direction is RecommendationDirection.BUY else "above"
    return _hit(bars, stop, side), stop


def _target_at(
    recommendation: Recommendation, bars: list[OHLCBar]
) -> tuple[int | None, float | None]:
    targets = [float(t) for t in (recommendation.targets_json or []) if isinstance(t, int | float)]
    if not targets:
        return None, None
    first = targets[0]
    side = "above" if recommendation.direction is RecommendationDirection.BUY else "below"
    return _hit(bars, first, side), first


async def evaluate_recommendation(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation: Recommendation,
    *,
    bars: list[OHLCBar],
    now: datetime | None = None,
) -> TrackerOutcome:
    """Advance one plan against the bars since it was written."""
    moment = now or datetime.now(UTC)
    await lock_recommendation(session, recommendation.id)
    previous = recommendation.status

    async def transition(status: RecommendationStatus, reason: str, detail: str) -> TrackerOutcome:
        try:
            assert_recommendation_transition(previous, status)
        except ValueError:
            # An illegal transition is a bug, and crashing the tracker over it
            # would stop every other plan in the workspace. Recorded and skipped.
            logger.warning(
                "tracker_illegal_transition",
                recommendation_id=str(recommendation.id),
                current=previous.value,
                attempted=status.value,
            )
            return TrackerOutcome(False, previous, reason="illegal_transition", detail=detail)
        recommendation.status = status
        recommendation.last_evaluated_at = moment
        if status is RecommendationStatus.ACTIVE:
            recommendation.activated_at = moment
        if status in TERMINAL_RECOMMENDATION_STATUSES:
            # Mirrors the execution axis onto its terminal value. Leaving it at
            # whatever creation set is how a finished plan keeps reading as
            # awaiting activation forever.
            recommendation.execution_state = (
                ExecutionState.INVALIDATED.value
                if status is RecommendationStatus.INVALIDATED
                else ExecutionState.EXPIRED.value
                if status is RecommendationStatus.EXPIRED
                else recommendation.execution_state
            )
        elif status is RecommendationStatus.READY:
            recommendation.execution_state = ExecutionState.VALID_NOW.value
        await session.flush()
        await record_revision(
            session,
            tenant,
            recommendation,
            reason=reason,
            previous_status=previous,
            changes={"detail": detail},
        )
        if status in TERMINAL_RECOMMENDATION_STATUSES:
            # The outcomes this loop produces are the ones nobody reported by
            # hand — the unflattering half of the sample. Skipping the hook
            # would leave M8 calibrating on volunteered wins.
            await on_recommendation_terminal_status(
                session, recommendation, new_status=status, facts={"source": "tracker"}
            )
        return TrackerOutcome(True, status, reason=reason, detail=detail)

    invalid_at, stop = _invalidated_at(recommendation, bars)
    target_at, target = _target_at(recommendation, bars)

    # First, and it wins ties. A plan whose stop broke is finished whatever
    # happened next — including reaching its target on the bounce, which without
    # this ordering would be recorded as a win.
    if invalid_at is not None and (target_at is None or invalid_at <= target_at):
        return await transition(
            RecommendationStatus.INVALIDATED,
            RevisionReason.INVALIDATION,
            f"stop {stop:g} traded through",
        )

    if target_at is not None:
        return await transition(
            RecommendationStatus.TARGET_REACHED,
            RevisionReason.TARGET_REACHED,
            f"target {target:g} reached",
        )

    if recommendation.status is RecommendationStatus.WAITING_CONFIRMATION:
        rule = parse_activation_rule(recommendation.activation_rule_json)
        if rule is not None:
            outcome = evaluate_activation(rule, bars)
            if outcome.satisfied:
                # READY, not ACTIVE: the condition firing means the plan is now
                # valid to take, not that anyone has taken it. Leovee never
                # executes, so "active" only ever describes a trade the user
                # reported themselves.
                return await transition(
                    RecommendationStatus.READY, RevisionReason.ACTIVATION, outcome.detail
                )

    if recommendation.expires_at is not None and moment >= _aware(recommendation.expires_at):
        return await transition(
            RecommendationStatus.EXPIRED,
            RevisionReason.EXPIRY,
            "the plan outlived its validity window",
        )

    recommendation.last_evaluated_at = moment
    await session.flush()
    return TrackerOutcome(False, previous)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)

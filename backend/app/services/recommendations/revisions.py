"""Recording why a recommendation changed.

Every transition writes one row. Not for completeness — because "this plan is
now invalidated" is only half an answer, and the half the user did not ask for.
They want to know *what happened*: the level broke, the session closed, the
re-evaluation found the structure gone.

**The sequence number is assigned in the database, not in Python.** The tracker
and a manual transition can land in the same millisecond, and a
read-max-then-write in application code gives them the same number. The unique
constraint would then reject one of them — losing a transition that actually
happened, which is worse than the collision it was meant to prevent.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationStatus
from app.models.recommendation import Recommendation, RecommendationRevision
from app.services.recommendations.repository import snapshot

__all__ = ["RevisionReason", "record_revision", "list_revisions", "latest_revision"]


class RevisionReason:
    """Why an evaluation ran. A closed vocabulary: free text here turns the
    history into prose that nothing can group or count."""

    CREATED = "created"
    REEVALUATION = "reevaluation"
    ACTIVATION = "activation"
    INVALIDATION = "invalidation"
    TARGET_REACHED = "target_reached"
    EXPIRY = "expiry"
    MANUAL = "manual"

    ALL = frozenset(
        {CREATED, REEVALUATION, ACTIVATION, INVALIDATION, TARGET_REACHED, EXPIRY, MANUAL}
    )


async def record_revision(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation: Recommendation,
    *,
    reason: str,
    previous_status: RecommendationStatus | None = None,
    changes: dict[str, Any] | None = None,
    note: str | None = None,
) -> RecommendationRevision:
    if reason not in RevisionReason.ALL:
        raise ValueError(f"unknown revision reason: {reason!r}")

    await bind_workspace_rls(session, tenant)
    # Assigned from the table under the row's lock rather than computed here:
    # two evaluations in the same millisecond would otherwise pick the same
    # number and the unique constraint would reject one, losing a transition
    # that really happened.
    next_seq = await session.scalar(
        select(func.coalesce(func.max(RecommendationRevision.seq), -1) + 1).where(
            RecommendationRevision.recommendation_id == recommendation.id
        )
    )
    row = RecommendationRevision(
        id=uuid.uuid4(),
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        recommendation_id=recommendation.id,
        seq=int(next_seq or 0),
        reason=reason,
        declared_status=recommendation.status.value,
        previous_status=previous_status.value if previous_status else None,
        snapshot_json=snapshot(recommendation),
        changes_json=changes or {},
        note=note,
    )
    session.add(row)
    await session.flush()
    return row


async def list_revisions(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation_id: uuid.UUID,
    *,
    limit: int = 50,
) -> Sequence[RecommendationRevision]:
    """Oldest first: the history reads as a story, not a stack."""
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        select(RecommendationRevision)
        .where(RecommendationRevision.recommendation_id == recommendation_id)
        .order_by(RecommendationRevision.seq.asc())
        .limit(limit)
    )
    return result.scalars().all()


async def latest_revision(
    session: AsyncSession, tenant: TenantContext, recommendation_id: uuid.UUID
) -> RecommendationRevision | None:
    """The newest revision — for explaining a change, never for rendering state.

    Rendering a badge from this shows the status that was true when the revision
    was written. A plan the tracker invalidated afterwards would still read
    READY. The row is the live state; this is history.
    """
    await bind_workspace_rls(session, tenant)
    row: RecommendationRevision | None = await session.scalar(
        select(RecommendationRevision)
        .where(RecommendationRevision.recommendation_id == recommendation_id)
        .order_by(RecommendationRevision.seq.desc())
        .limit(1)
    )
    return row


async def lock_recommendation(session: AsyncSession, recommendation_id: uuid.UUID) -> None:
    """Serialise concurrent evaluations of one recommendation.

    The tracker, a re-evaluation and a manual transition can all touch the same
    row at once, and without this two of them read the same status, both decide
    a transition is legal from it, and the second silently overwrites the first.
    """
    await session.execute(
        text("SELECT id FROM recommendations WHERE id = :rid FOR UPDATE"),
        {"rid": recommendation_id},
    )

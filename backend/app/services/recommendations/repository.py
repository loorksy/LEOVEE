"""Reading and writing recommendations, with no way to name a scope.

**Not one function here accepts a user id, a workspace id or a tenant id as a
filter.** That is the whole design, and it is a direct response to what the
reference implementation does: AiChart threads `userId` through six hundred
lines of hand-written `WHERE` clauses, one per query, and the isolation of the
entire product rests on nobody ever forgetting one. Porting that signature would
port the bug class with it.

Here the scope comes from the session. `bind_workspace_rls` sets the Postgres
session variables the policies read, and the database filters every statement
whether the caller remembered to or not. A cross-tenant query is not *guarded
against* — it is **inexpressible**: there is no argument to pass that would
widen the scope, and a caller who wanted one would have to change the policy.

A conformance test asserts the absence, because the property is only true while
nobody adds a convenient `workspace_id=` parameter to "make a report easier".
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationStatus
from app.models.recommendation import Recommendation
from app.schemas.decision import ExecutionState, PlanType
from app.services.recommendation_lifecycle import TERMINAL_RECOMMENDATION_STATUSES

__all__ = [
    "OPEN_STATUSES",
    "list_open",
    "list_recent",
    "get",
    "list_by_status",
    "list_awaiting_activation",
    "list_stale",
    "assert_axes_coherent",
]

#: Everything that has not finished. Derived from the terminal set rather than
#: listed, so a new status joins the right side automatically instead of
#: silently dropping out of every open-recommendation query.
OPEN_STATUSES: frozenset[RecommendationStatus] = frozenset(
    status for status in RecommendationStatus if status not in TERMINAL_RECOMMENDATION_STATUSES
)


def _base() -> Select[tuple[Recommendation]]:
    """Every query starts here, and it carries no tenant predicate.

    Deliberately: adding one would be harmless but misleading, implying the
    filtering happens in Python. It happens in the database, and a reader who
    believes otherwise will "helpfully" add the parameter this module exists
    without.
    """
    return select(Recommendation)


async def list_open(
    session: AsyncSession, tenant: TenantContext, *, limit: int = 100
) -> Sequence[Recommendation]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        _base()
        .where(Recommendation.status.in_(OPEN_STATUSES))
        .order_by(Recommendation.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def list_recent(
    session: AsyncSession, tenant: TenantContext, *, limit: int = 50
) -> Sequence[Recommendation]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(_base().order_by(Recommendation.created_at.desc()).limit(limit))
    return result.scalars().all()


async def get(
    session: AsyncSession, tenant: TenantContext, recommendation_id: uuid.UUID
) -> Recommendation | None:
    """One row, or nothing.

    A row belonging to another workspace returns None rather than raising: the
    caller must not be able to tell "does not exist" from "not yours", or the
    endpoint becomes an existence oracle for other tenants' ids.
    """
    await bind_workspace_rls(session, tenant)
    row: Recommendation | None = await session.scalar(
        _base().where(Recommendation.id == recommendation_id)
    )
    return row


async def list_by_status(
    session: AsyncSession,
    tenant: TenantContext,
    statuses: Sequence[RecommendationStatus],
    *,
    limit: int = 100,
) -> Sequence[Recommendation]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        _base()
        .where(Recommendation.status.in_(list(statuses)))
        .order_by(Recommendation.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def list_awaiting_activation(
    session: AsyncSession, tenant: TenantContext, *, limit: int = 100
) -> Sequence[Recommendation]:
    """Plans whose entry condition has not fired.

    These are what the tracker polls: every one of them is a trade the user was
    told to wait for, and a condition that fires unnoticed is the plan failing
    quietly at the exact moment it was supposed to work.
    """
    return await list_by_status(
        session,
        tenant,
        [RecommendationStatus.WAITING_CONFIRMATION, RecommendationStatus.FORMING],
        limit=limit,
    )


async def list_stale(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    older_than: datetime,
    limit: int = 100,
) -> Sequence[Recommendation]:
    """Open plans that have outlived their usefulness.

    Expiry is a real outcome, not housekeeping: a plan still shown as live three
    sessions after the structure that justified it disappeared is worse than no
    plan, because it carries the authority of the analysis that produced it.
    """
    await bind_workspace_rls(session, tenant)
    cutoff = older_than if older_than.tzinfo else older_than.replace(tzinfo=UTC)
    result = await session.execute(
        _base()
        .where(Recommendation.status.in_(OPEN_STATUSES), Recommendation.created_at < cutoff)
        .order_by(Recommendation.created_at.asc())
        .limit(limit)
    )
    return result.scalars().all()


def snapshot(recommendation: Recommendation) -> dict[str, Any]:
    """The fields a revision records. Not the ORM row — a revision is a fact
    about a past state, and holding a live object would let it change."""
    return {
        "status": recommendation.status.value,
        "direction": recommendation.direction.value,
        "entry": float(recommendation.entry) if recommendation.entry is not None else None,
        "stop": float(recommendation.stop) if recommendation.stop is not None else None,
        "targets": list(recommendation.targets_json or []),
        "confidence": (
            float(recommendation.confidence_calibrated)
            if recommendation.confidence_calibrated is not None
            else None
        ),
    }


def assert_axes_coherent(*, plan_type: str | None, execution_state: str | None) -> None:
    """The one cross-layer rule between the three axes.

    A conditional plan cannot be valid *now* — it is waiting for its stated
    trigger, and that is the entire meaning of the word. The combination reads
    as an immediate plan to everything downstream while telling the user to
    wait, and the two audiences then see different things.

    Every other pairing is legitimate: an immediate plan can be blocked, an
    anticipatory one can be valid now if price came to it.
    """
    if (
        plan_type == PlanType.CONDITIONAL.value
        and execution_state == ExecutionState.VALID_NOW.value
    ):
        raise ValueError("a conditional plan cannot be valid_now — it waits for its stated trigger")

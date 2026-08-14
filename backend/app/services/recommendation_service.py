from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationDirection, RecommendationStatus, ThesisStatus
from app.models.recommendation import Recommendation, Thesis
from app.services import market_data
from app.services.recommendation_lifecycle import (
    TERMINAL_RECOMMENDATION_STATUSES,
    assert_recommendation_transition,
)
from app.services.recommendations.repository import assert_axes_coherent


async def create_recommendation(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol_code: str,
    direction: RecommendationDirection,
    status: RecommendationStatus = RecommendationStatus.DETECTED,
    evidence: dict[str, Any] | None = None,
    agent_run_id: uuid.UUID | None = None,
    confidence: Decimal | None = None,
    entry: Decimal | None = None,
    stop: Decimal | None = None,
    targets: list[float] | None = None,
    timeframe: str | None = None,
    plan_type: str | None = None,
    execution_state: str | None = None,
    activation_rule: dict[str, Any] | None = None,
    activation_condition: str | None = None,
    expires_at: datetime | None = None,
    tradability: str | None = None,
    tradability_reason: str | None = None,
) -> Recommendation:
    # The one cross-layer rule: a conditional plan cannot be valid *now*, which
    # is the entire meaning of the word. The pairing reads as immediate to
    # everything downstream while the user is told to wait.
    assert_axes_coherent(plan_type=plan_type, execution_state=execution_state)
    await bind_workspace_rls(session, tenant)
    symbol = await market_data.get_or_create_symbol(session, symbol_code)
    rec = Recommendation(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol_id=symbol.id,
        direction=direction,
        status=status,
        evidence_json=evidence or {},
        agent_run_id=agent_run_id,
        # None, not 0.5. The hardcoded half was written to every row including
        # the NO_TRADE ones — a confidence figure attached to a failed analysis,
        # which ADR 0002 forbids precisely because a reader takes it for a weak
        # opinion when it is the absence of one. A missing confidence is a fact
        # the column can express; an invented one is not.
        confidence_calibrated=confidence,
        entry=entry,
        stop=stop,
        targets_json=targets or [],
        timeframe=timeframe,
        plan_type=plan_type,
        execution_state=execution_state,
        activation_rule_json=activation_rule,
        activation_condition=activation_condition,
        expires_at=expires_at,
        tradability=tradability,
        tradability_reason=tradability_reason,
    )
    session.add(rec)
    await session.flush()
    return rec


async def list_recommendations(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    limit: int = 50,
) -> list[Recommendation]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        select(Recommendation)
        .where(
            Recommendation.tenant_id == tenant.tenant_id,
            Recommendation.workspace_id == tenant.workspace_id,
        )
        .order_by(Recommendation.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_recommendation(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation_id: uuid.UUID,
) -> Recommendation | None:
    await bind_workspace_rls(session, tenant)
    rec = await session.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.tenant_id == tenant.tenant_id,
            Recommendation.workspace_id == tenant.workspace_id,
        )
    )
    return rec


async def spawn_thesis_from_recommendation(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation: Recommendation,
    *,
    statement: str | None = None,
) -> Thesis:
    await bind_workspace_rls(session, tenant)
    default_statement = f"Thesis for {recommendation.direction.value}"
    thesis = Thesis(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        recommendation_id=recommendation.id,
        statement=statement or recommendation.thesis_text or default_statement,
        status=ThesisStatus.ACTIVE,
    )
    session.add(thesis)
    await session.flush()
    return thesis


async def list_theses(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    limit: int = 50,
) -> list[Thesis]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        select(Thesis)
        .where(
            Thesis.tenant_id == tenant.tenant_id,
            Thesis.workspace_id == tenant.workspace_id,
        )
        .order_by(Thesis.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def resolve_symbol_code(session: AsyncSession, symbol_id: uuid.UUID) -> str | None:
    from app.models.symbol import Symbol

    row = await session.scalar(select(Symbol).where(Symbol.id == symbol_id))
    return row.code if row else None


def recommendation_to_card(
    rec: Recommendation,
    *,
    symbol_code: str | None = None,
) -> dict[str, Any]:
    # None, not 0.0. A card reading "0% confidence" looks like a very weak
    # opinion; the absence of one is a different fact, and the only one a
    # degraded run has to report.
    confidence = None if rec.confidence_calibrated is None else float(rec.confidence_calibrated)
    return {
        "id": str(rec.id),
        "symbol": symbol_code,
        "direction": rec.direction.value,
        "status": rec.status.value,
        "confidence": confidence,
        "headline": f"{symbol_code or 'SYMBOL'} {rec.direction.value}",
        "thesis": rec.thesis_text,
        # A missing confidence gets no badge rather than a "conf:0%" one, which
        # would read as a measured zero.
        "badges": [rec.status.value, *([] if confidence is None else [f"conf:{confidence:.0%}"])],
        "entry": float(rec.entry) if rec.entry is not None else None,
        "stop": float(rec.stop) if rec.stop is not None else None,
        "targets": rec.targets_json,
        "evidence_preview": (rec.evidence_json or {}).get("engines", {}),
    }


async def transition_recommendation_status(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation_id: uuid.UUID,
    *,
    new_status: RecommendationStatus,
    facts: dict[str, Any] | None = None,
) -> Recommendation | None:
    """Move a plan, under the same lock the tracker takes.

    Two things were missing here, and both let one closed plan be counted twice.

    **The lock.** `lock_recommendation` is documented as serialising "the
    tracker, a re-evaluation and a manual transition", and this — the manual
    transition, also reached from the thesis-monitor worker — was the one caller
    that never took it. Without it two writers read the same non-terminal status,
    both pass the state machine, and both record an outcome.

    **The already-terminal guard.** `assert_recommendation_transition` returns
    *silently* when the current status already equals the requested one, so a
    retried request or a user closing a plan the tracker just closed passed
    straight through and re-fired the learning hook. A plan finishes once; a
    second request to finish it is a no-op, not an error.
    """
    from app.services.recommendations.revisions import lock_recommendation

    rec = await get_recommendation(session, tenant, recommendation_id)
    if rec is None:
        return None
    await lock_recommendation(session, rec.id)
    # Re-read under the lock: the row this session loaded may have been moved to
    # a terminal status by the tracker while we waited for it.
    await session.refresh(rec)
    if rec.status in TERMINAL_RECOMMENDATION_STATUSES:
        return rec
    assert_recommendation_transition(rec.status, new_status)
    rec.status = new_status
    await session.flush()
    from app.services.learning.terminal_hooks import on_recommendation_terminal_status

    await on_recommendation_terminal_status(session, rec, new_status=new_status, facts=facts)
    return rec


async def transition_thesis_status(
    session: AsyncSession,
    tenant: TenantContext,
    thesis_id: uuid.UUID,
    *,
    new_status: ThesisStatus,
    r_multiple: Decimal | None = None,
    facts: dict[str, Any] | None = None,
) -> Thesis | None:
    thesis = await session.scalar(
        select(Thesis).where(
            Thesis.id == thesis_id,
            Thesis.tenant_id == tenant.tenant_id,
            Thesis.workspace_id == tenant.workspace_id,
        )
    )
    if thesis is None:
        return None
    rec = await get_recommendation(session, tenant, thesis.recommendation_id)
    if rec is None:
        return None
    thesis.status = new_status
    await session.flush()
    from app.services.learning.terminal_hooks import on_thesis_terminal_status

    await on_thesis_terminal_status(
        session,
        thesis,
        rec,
        new_status=new_status,
        r_multiple=r_multiple,
        facts=facts,
    )
    return thesis

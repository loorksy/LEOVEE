from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationDirection, RecommendationStatus, ThesisStatus
from app.models.recommendation import Recommendation, Thesis
from app.services import market_data
from app.services.recommendation_lifecycle import assert_recommendation_transition


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
) -> Recommendation:
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
    rec = await get_recommendation(session, tenant, recommendation_id)
    if rec is None:
        return None
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

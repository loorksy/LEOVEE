from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.enums import RecommendationDirection, RecommendationStatus, ThesisStatus
from app.models.recommendation import Recommendation, Thesis
from app.services import market_data


async def create_recommendation(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol_code: str,
    direction: RecommendationDirection,
    status: RecommendationStatus = RecommendationStatus.DETECTED,
    evidence: dict[str, Any] | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> Recommendation:
    symbol = await market_data.get_or_create_symbol(session, symbol_code)
    rec = Recommendation(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol_id=symbol.id,
        direction=direction,
        status=status,
        evidence_json=evidence or {},
        agent_run_id=agent_run_id,
        confidence_calibrated=Decimal("0.5"),
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

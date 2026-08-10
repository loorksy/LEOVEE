from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.engines.thesis_monitor import evaluate_thesis_monitor
from app.models.enums import RecommendationStatus, ThesisStatus
from app.models.recommendation import Recommendation, Thesis
from app.models.thesis_event import ThesisEvent
from app.services import recommendation_service


async def record_thesis_event(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    thesis_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> ThesisEvent:
    await bind_workspace_rls(session, tenant)
    event = ThesisEvent(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        thesis_id=thesis_id,
        event_type=event_type,
        payload_json=payload,
    )
    session.add(event)
    await session.flush()
    return event


async def monitor_thesis_row(
    session: AsyncSession,
    tenant: TenantContext,
    thesis: Thesis,
    recommendation: Recommendation,
    *,
    last_price: Decimal,
    structure: dict[str, Any],
) -> dict[str, Any]:
    invalidation = {**thesis.invalidation_json, **(recommendation.invalidation_json or {})}
    proposal = evaluate_thesis_monitor(
        thesis_status=thesis.status.value,
        direction=recommendation.direction.value,
        last_price=last_price,
        structure=structure,
        invalidation=invalidation,
    )
    if proposal.get("action") != "TRANSITION":
        return {"thesis_id": str(thesis.id), "changed": False}

    new_status = ThesisStatus(proposal["new_status"])
    await record_thesis_event(
        session,
        tenant,
        thesis_id=thesis.id,
        event_type=str(proposal["event_type"]),
        payload={
            "reason": proposal.get("reason"),
            "last_price": float(last_price),
            "structure": structure,
        },
    )
    await recommendation_service.transition_thesis_status(
        session,
        tenant,
        thesis.id,
        new_status=new_status,
        facts={"monitor": proposal},
    )
    rec_status_map = {
        ThesisStatus.INVALIDATED: RecommendationStatus.INVALIDATED,
        ThesisStatus.TARGET_REACHED: RecommendationStatus.TARGET_REACHED,
        ThesisStatus.EXPIRED: RecommendationStatus.EXPIRED,
    }
    rec_status = rec_status_map.get(new_status)
    if rec_status is not None:
        await recommendation_service.transition_recommendation_status(
            session,
            tenant,
            recommendation.id,
            new_status=rec_status,
            facts={"thesis_monitor": proposal},
        )
    return {"thesis_id": str(thesis.id), "changed": True, "new_status": new_status.value}


async def list_active_theses(session: AsyncSession) -> list[tuple[Thesis, Recommendation]]:
    """Privileged batch scan (worker sets GUC per workspace in outer loop)."""
    result = await session.execute(
        select(Thesis, Recommendation)
        .join(Recommendation, Recommendation.id == Thesis.recommendation_id)
        .where(
            Thesis.status.in_(
                [
                    ThesisStatus.ACTIVE,
                    ThesisStatus.STRENGTHENING,
                    ThesisStatus.WEAKENING,
                ]
            )
        )
    )
    return [(thesis, rec) for thesis, rec in result.all()]

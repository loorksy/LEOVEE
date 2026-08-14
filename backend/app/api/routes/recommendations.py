from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.services import recommendation_service
from app.services.recommendations import repository, revisions

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


class RecommendationCreate(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    direction: RecommendationDirection
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecommendationStatusUpdate(BaseModel):
    status: RecommendationStatus
    facts: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_recommendations(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    cards: bool = False,
) -> dict[str, Any]:
    rows = await recommendation_service.list_recommendations(session, tenant)
    if not cards:
        return {
            "items": [
                {
                    "id": str(r.id),
                    "symbol_id": str(r.symbol_id),
                    "direction": r.direction.value,
                    "status": r.status.value,
                    "confidence": float(r.confidence_calibrated or 0),
                }
                for r in rows
            ]
        }
    items = []
    for rec in rows:
        symbol_code = await recommendation_service.resolve_symbol_code(session, rec.symbol_id)
        items.append(recommendation_service.recommendation_to_card(rec, symbol_code=symbol_code))
    return {"items": items}


@router.post("")
async def create_recommendation(
    body: RecommendationCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    rec = await recommendation_service.create_recommendation(
        session,
        tenant,
        symbol_code=body.symbol.upper(),
        direction=body.direction,
        evidence=body.evidence,
    )
    return {"id": str(rec.id)}


@router.get("/{recommendation_id}")
async def get_recommendation(
    recommendation_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    card: bool = False,
) -> dict[str, Any]:
    rec = await recommendation_service.get_recommendation(session, tenant, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    symbol_code = await recommendation_service.resolve_symbol_code(session, rec.symbol_id)
    if card:
        return recommendation_service.recommendation_to_card(rec, symbol_code=symbol_code)
    return {
        "id": str(rec.id),
        "symbol": symbol_code,
        "direction": rec.direction.value,
        "status": rec.status.value,
        "evidence": rec.evidence_json,
        "thesis": rec.thesis_text,
        "confidence": float(rec.confidence_calibrated or 0),
    }


@router.patch("/{recommendation_id}/status")
async def update_recommendation_status(
    recommendation_id: uuid.UUID,
    body: RecommendationStatusUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    try:
        rec = await recommendation_service.transition_recommendation_status(
            session,
            tenant,
            recommendation_id,
            new_status=body.status,
            facts=body.facts,
        )
    except ValueError as exc:
        if str(exc).startswith("invalid_transition"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        raise
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    symbol_code = await recommendation_service.resolve_symbol_code(session, rec.symbol_id)
    return {
        "id": str(rec.id),
        "status": rec.status.value,
        "card": recommendation_service.recommendation_to_card(rec, symbol_code=symbol_code),
        "terminal_outcome_recorded": rec.status
        in {
            RecommendationStatus.TARGET_REACHED,
            RecommendationStatus.INVALIDATED,
            RecommendationStatus.EXPIRED,
        },
    }


@router.get("/{recommendation_id}/revisions")
async def get_revisions(
    recommendation_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    """Why this plan changed, oldest first.

    The history reads as a story rather than a stack. Note what it deliberately
    does *not* do: it never becomes the source for the card's badge. The newest
    revision holds the status that was true when it was written, so a plan the
    tracker moved afterwards would render with a status it no longer has.
    """
    if await repository.get(session, tenant, recommendation_id) is None:
        # None, not 403. A caller must not be able to tell "not yours" from
        # "does not exist", or the endpoint is an existence oracle for other
        # tenants' identifiers.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    rows = await revisions.list_revisions(session, tenant, recommendation_id)
    return {
        "items": [
            {
                "seq": row.seq,
                "reason": row.reason,
                "declared_status": row.declared_status,
                "previous_status": row.previous_status,
                "snapshot": row.snapshot_json,
                "changes": row.changes_json,
                "note": row.note,
                "at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/open")
async def list_open_recommendations(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    """Everything still live, with what it is waiting for.

    `tradability` is a separate axis from confidence and is reported as one: a
    plan can be entirely convincing and untradeable because the entry is far or
    the session is closed, and folding that into the confidence figure would say
    the analysis is weak when the moment is simply wrong.
    """
    rows = await repository.list_open(session, tenant)
    return {
        "items": [
            {
                "id": str(row.id),
                "direction": row.direction.value,
                "status": row.status.value,
                "timeframe": row.timeframe,
                "plan_type": row.plan_type,
                "execution_state": row.execution_state,
                "tradability": row.tradability,
                "tradability_reason": row.tradability_reason,
                "activation_condition": row.activation_condition,
                "entry": float(row.entry) if row.entry is not None else None,
                "stop": float(row.stop) if row.stop is not None else None,
                "targets": row.targets_json,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "last_evaluated_at": (
                    row.last_evaluated_at.isoformat() if row.last_evaluated_at else None
                ),
            }
            for row in rows
        ]
    }

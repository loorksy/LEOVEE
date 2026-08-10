from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.enums import RecommendationDirection
from app.services import recommendation_service

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


class RecommendationCreate(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    direction: RecommendationDirection
    evidence: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_recommendations(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    rows = await recommendation_service.list_recommendations(session, tenant)
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
) -> dict[str, Any]:
    rec = await recommendation_service.get_recommendation(session, tenant, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {
        "id": str(rec.id),
        "direction": rec.direction.value,
        "status": rec.status.value,
        "evidence": rec.evidence_json,
    }

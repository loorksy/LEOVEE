from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.services import recommendation_service

router = APIRouter(prefix="/api/v1/theses", tags=["theses"])


class ThesisCreate(BaseModel):
    recommendation_id: uuid.UUID
    statement: str | None = Field(default=None, max_length=4000)


@router.get("")
async def list_theses(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, object]:
    rows = await recommendation_service.list_theses(session, tenant)
    return {
        "items": [
            {
                "id": str(t.id),
                "recommendation_id": str(t.recommendation_id),
                "statement": t.statement,
                "status": t.status.value,
            }
            for t in rows
        ]
    }


@router.post("")
async def create_thesis(
    body: ThesisCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    rec = await recommendation_service.get_recommendation(session, tenant, body.recommendation_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found",
        )
    thesis = await recommendation_service.spawn_thesis_from_recommendation(
        session,
        tenant,
        rec,
        statement=body.statement,
    )
    return {"id": str(thesis.id)}

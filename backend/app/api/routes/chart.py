from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.schemas.chart import ChartAnnotationCreate
from app.services import chart_semantic_service
from app.services.chart_semantic_service import ChartSemanticValidationError

router = APIRouter(prefix="/api/v1/chart", tags=["chart"])


class SemanticModelPayload(BaseModel):
    model: dict[str, Any]


@router.get("/annotations")
async def list_chart_annotations(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    analysis_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    rows = await chart_semantic_service.list_annotations(
        session,
        tenant,
        analysis_id=analysis_id,
    )
    return {"items": [chart_semantic_service.annotation_to_dict(r) for r in rows]}


@router.post("/annotations", status_code=status.HTTP_201_CREATED)
async def create_chart_annotation(
    body: ChartAnnotationCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    try:
        row = await chart_semantic_service.create_annotation(
            session,
            tenant,
            semantic_type=body.semantic_type,
            geometry_json=body.geometry_json,
            style_json=body.style_json,
            analysis_id=uuid.UUID(body.analysis_id) if body.analysis_id else None,
            recommendation_id=uuid.UUID(body.recommendation_id) if body.recommendation_id else None,
            thesis_id=uuid.UUID(body.thesis_id) if body.thesis_id else None,
        )
    except ChartSemanticValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return {"id": str(row.id)}


@router.post("/semantic/validate")
async def validate_semantic_model(body: SemanticModelPayload) -> dict[str, Any]:
    try:
        model = chart_semantic_service.validate_semantic_model(body.model)
    except ChartSemanticValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {"valid": True, "operation_count": len(model.operations)}

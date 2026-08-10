from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.engines.chart_semantic import build_chart_semantic_model
from app.infrastructure.database import get_db_session
from app.models.chart_annotation import ChartAnnotationStatus
from app.schemas.chart import ChartAnnotationCreate
from app.services import chart_semantic_service
from app.services.chart_semantic_service import ChartSemanticValidationError

router = APIRouter(prefix="/api/v1/chart", tags=["chart"])


class SemanticModelPayload(BaseModel):
    model: dict[str, Any]


class BuildSemanticPayload(BaseModel):
    symbol: str = Field(min_length=3, max_length=16)
    timeframe: str = Field(default="H1", max_length=8)
    as_of: str
    engines: dict[str, Any]


class AnnotationStatusUpdate(BaseModel):
    status: ChartAnnotationStatus


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


@router.patch("/annotations/{annotation_id}")
async def update_chart_annotation_status(
    annotation_id: uuid.UUID,
    body: AnnotationStatusUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    row = await chart_semantic_service.transition_annotation_status(
        session,
        tenant,
        annotation_id,
        status=body.status,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    await session.commit()
    return chart_semantic_service.annotation_to_dict(row)


@router.post("/semantic/validate")
async def validate_semantic_model(body: SemanticModelPayload) -> dict[str, Any]:
    try:
        model = chart_semantic_service.validate_semantic_model(body.model)
    except ChartSemanticValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {"valid": True, "operation_count": len(model.operations)}


@router.post("/semantic/build")
async def build_semantic_from_engines(body: BuildSemanticPayload) -> dict[str, Any]:
    from datetime import datetime

    try:
        as_of = datetime.fromisoformat(body.as_of.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid as_of timestamp"
        ) from exc
    model = build_chart_semantic_model(
        symbol=body.symbol.upper(),
        timeframe=body.timeframe,
        as_of=as_of,
        engines=body.engines,
    )
    return {"model": model.model_dump()}


@router.post("/semantic/persist", status_code=status.HTTP_201_CREATED)
async def persist_semantic_model(
    body: SemanticModelPayload,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    analysis_id: uuid.UUID | None = None,
    recommendation_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    try:
        model = chart_semantic_service.validate_semantic_model(body.model)
    except ChartSemanticValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    rows = await chart_semantic_service.persist_semantic_model(
        session,
        tenant,
        model,
        analysis_id=analysis_id,
        recommendation_id=recommendation_id,
    )
    await session.commit()
    return {
        "ids": [str(r.id) for r in rows],
        "count": len(rows),
        "version": model.version,
    }

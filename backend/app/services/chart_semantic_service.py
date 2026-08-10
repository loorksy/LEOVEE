from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.chart_annotation import ChartAnnotation, ChartAnnotationStatus
from app.schemas.chart import ChartGeometry, ChartSemanticModel, ChartSemanticOperation


class ChartSemanticValidationError(ValueError):
    pass


def validate_geometry(geometry_json: dict[str, Any]) -> ChartGeometry:
    try:
        return ChartGeometry.model_validate(geometry_json)
    except ValidationError as exc:
        raise ChartSemanticValidationError(str(exc)) from exc


def validate_semantic_model(payload: dict[str, Any]) -> ChartSemanticModel:
    try:
        return ChartSemanticModel.model_validate(payload)
    except ValidationError as exc:
        raise ChartSemanticValidationError(str(exc)) from exc


async def list_annotations(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    analysis_id: uuid.UUID | None = None,
    limit: int = 200,
) -> list[ChartAnnotation]:
    query = select(ChartAnnotation).where(
        ChartAnnotation.tenant_id == tenant.tenant_id,
        ChartAnnotation.workspace_id == tenant.workspace_id,
    )
    if analysis_id is not None:
        query = query.where(ChartAnnotation.analysis_id == analysis_id)
    query = query.order_by(ChartAnnotation.updated_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_annotation(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    semantic_type: str,
    geometry_json: dict[str, Any],
    style_json: dict[str, Any],
    analysis_id: uuid.UUID | None = None,
    recommendation_id: uuid.UUID | None = None,
    thesis_id: uuid.UUID | None = None,
) -> ChartAnnotation:
    validate_geometry(geometry_json)
    row = ChartAnnotation(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        semantic_type=semantic_type,
        geometry_json=geometry_json,
        style_json=style_json,
        analysis_id=analysis_id,
        recommendation_id=recommendation_id,
        thesis_id=thesis_id,
        status=ChartAnnotationStatus.ACTIVE,
    )
    session.add(row)
    await session.flush()
    return row


def annotation_to_dict(row: ChartAnnotation) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "semantic_type": row.semantic_type,
        "geometry": row.geometry_json,
        "style": row.style_json,
        "status": row.status.value,
        "version": row.version,
        "analysis_id": str(row.analysis_id) if row.analysis_id else None,
        "recommendation_id": str(row.recommendation_id) if row.recommendation_id else None,
        "thesis_id": str(row.thesis_id) if row.thesis_id else None,
    }


def operations_from_model(model: ChartSemanticModel) -> list[ChartSemanticOperation]:
    return list(model.operations)

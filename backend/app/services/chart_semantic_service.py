from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.infrastructure.realtime import annotation_broadcaster
from app.models.chart_annotation import ChartAnnotation, ChartAnnotationStatus
from app.schemas.chart import ChartGeometry, ChartSemanticModel, ChartSemanticOperation


class ChartSemanticValidationError(ValueError):
    pass


_FORBIDDEN_GEOMETRY_KEYS = frozenset(
    {"x", "y", "screen_x", "screen_y", "pixel_x", "pixel_y", "left", "top", "width", "height"}
)


def _reject_screen_geometry(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in _FORBIDDEN_GEOMETRY_KEYS:
                raise ChartSemanticValidationError(
                    f"geometry must use timestamp and price anchors only, not screen key '{key}'"
                )
            _reject_screen_geometry(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_screen_geometry(item)


def validate_geometry(geometry_json: dict[str, Any]) -> ChartGeometry:
    _reject_screen_geometry(geometry_json)
    try:
        return ChartGeometry.model_validate(geometry_json)
    except ValidationError as exc:
        raise ChartSemanticValidationError(str(exc)) from exc


def validate_semantic_model(payload: dict[str, Any]) -> ChartSemanticModel:
    try:
        model = ChartSemanticModel.model_validate(payload)
    except ValidationError as exc:
        raise ChartSemanticValidationError(str(exc)) from exc
    for op in model.operations:
        _reject_screen_geometry(op.geometry.model_dump())
    return model


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
    agent_run_id: uuid.UUID | None = None,
    status: ChartAnnotationStatus = ChartAnnotationStatus.ACTIVE,
    publish: bool = True,
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
        agent_run_id=agent_run_id,
        status=status,
    )
    session.add(row)
    await session.flush()
    if publish:
        await publish_annotation_event(tenant, row, event="annotation_created")
    return row


async def persist_semantic_model(
    session: AsyncSession,
    tenant: TenantContext,
    model: ChartSemanticModel,
    *,
    analysis_id: uuid.UUID | None = None,
    recommendation_id: uuid.UUID | None = None,
    thesis_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> list[ChartAnnotation]:
    rows: list[ChartAnnotation] = []
    for op in model.operations:
        row = await create_annotation(
            session,
            tenant,
            semantic_type=op.semantic_type.value,
            geometry_json=op.geometry.model_dump(),
            style_json=op.style.model_dump(exclude_none=True),
            analysis_id=analysis_id,
            recommendation_id=recommendation_id,
            thesis_id=thesis_id,
            agent_run_id=agent_run_id,
            publish=False,
        )
        rows.append(row)
    if rows:
        await publish_annotation_event(
            tenant,
            rows[-1],
            event="annotations_batch",
            extra={"count": len(rows)},
        )
    return rows


async def transition_annotation_status(
    session: AsyncSession,
    tenant: TenantContext,
    annotation_id: uuid.UUID,
    *,
    status: ChartAnnotationStatus,
) -> ChartAnnotation | None:
    row = await session.scalar(
        select(ChartAnnotation).where(
            ChartAnnotation.id == annotation_id,
            ChartAnnotation.tenant_id == tenant.tenant_id,
            ChartAnnotation.workspace_id == tenant.workspace_id,
        )
    )
    if row is None:
        return None
    row.status = status
    row.version = row.version + 1
    await session.flush()
    await publish_annotation_event(tenant, row, event="annotation_updated")
    return row


async def publish_annotation_event(
    tenant: TenantContext,
    row: ChartAnnotation,
    *,
    event: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if tenant.workspace_id is None:
        return
    payload: dict[str, Any] = {
        "event": event,
        "annotation": annotation_to_dict(row),
    }
    if extra:
        payload.update(extra)
    await annotation_broadcaster.publish(str(tenant.workspace_id), payload)


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

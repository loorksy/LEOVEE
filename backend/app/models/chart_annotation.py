from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.mixins import WorkspaceOwnedMixin


class ChartAnnotationStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ChartAnnotation(Base, TimestampMixin, WorkspaceOwnedMixin):
    __tablename__ = "chart_annotations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    semantic_type: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    style_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ChartAnnotationStatus] = mapped_column(
        Enum(ChartAnnotationStatus, name="chart_annotation_status"),
        nullable=False,
        default=ChartAnnotationStatus.CREATED,
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1)

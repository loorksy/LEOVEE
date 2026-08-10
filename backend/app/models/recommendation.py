from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import RecommendationDirection, RecommendationStatus, ThesisStatus
from app.models.mixins import WorkspaceOwnedMixin


class Recommendation(Base, TimestampMixin, WorkspaceOwnedMixin):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id"), nullable=False, index=True
    )
    direction: Mapped[RecommendationDirection] = mapped_column(
        Enum(RecommendationDirection, name="recommendation_direction"),
        nullable=False,
    )
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus, name="recommendation_status"),
        nullable=False,
        default=RecommendationStatus.DETECTED,
    )
    entry: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    targets_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    rr_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    confidence_calibrated: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    thesis_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    contradicting_evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    invalidation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    memory_citations_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    data_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class Thesis(Base, TimestampMixin, WorkspaceOwnedMixin):
    __tablename__ = "theses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ThesisStatus] = mapped_column(
        Enum(ThesisStatus, name="thesis_status"),
        nullable=False,
        default=ThesisStatus.ACTIVE,
    )
    invalidation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    monitor_config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

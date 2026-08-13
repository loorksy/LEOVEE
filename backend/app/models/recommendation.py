from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
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

    # --- lifecycle (M7) ---
    #
    # These live on the row, not derived from the newest revision. A card reads
    # the row: a plan the tracker invalidated after the last evaluation would
    # otherwise still show the status that evaluation declared.
    timeframe: Mapped[str | None] = mapped_column(String(8), nullable=True)
    plan_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: The third axis of the decision contract (ADR 0002), persisted rather than
    #: left in the analysis response. Without it, "waiting on its trigger" and
    #: "valid right now" are indistinguishable the moment the request ends.
    execution_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    #: The condition, as data the worker evaluates rather than prose a person
    #: reads. Prose alone is how a conditional plan sits at "awaiting
    #: activation" through the whole move it was waiting for.
    activation_rule_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    activation_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Expiry is an outcome, not housekeeping: a plan still shown as live three
    #: sessions after its structure disappeared carries the authority of the
    #: analysis that produced it.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tradability: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tradability_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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


class RecommendationRevision(Base, TimestampMixin, WorkspaceOwnedMixin):
    """What one evaluation *declared*, kept as history.

    The distinction from the row is the whole point, and it is easy to get
    backwards. A revision is a fact about a past moment; the row is the live
    state. A card that renders its badge from the newest revision shows the
    status that was true when that revision was written — so a plan the tracker
    invalidated five minutes later still reads READY, with the authority of the
    analysis behind it.

    History answers "why did this change". The row answers "what is it now".
    """

    __tablename__ = "recommendation_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Monotonic per recommendation. Ordering by timestamp alone breaks when two
    #: evaluations land in the same millisecond, which the tracker does.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    changes_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

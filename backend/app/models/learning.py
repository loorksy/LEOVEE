from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.mixins import WorkspaceOwnedMixin


class AgentRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentRun(Base, WorkspaceOwnedMixin, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="RUNNING")
    status: Mapped[AgentRunStatus] = mapped_column(String(32), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memories_retrieved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutcomeRecord(Base, WorkspaceOwnedMixin, TimestampMixin):
    __tablename__ = "outcome_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    trade_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="LIVE")
    facts_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorder_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")


class StrategyStat(Base, WorkspaceOwnedMixin, TimestampMixin):
    __tablename__ = "strategy_stats"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "strategy_code",
            "setup_type",
            "regime_bucket",
            "session_bucket",
            "volatility_bucket",
            name="uq_strategy_stat_bucket",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    strategy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    setup_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ANY")
    regime_bucket: Mapped[str] = mapped_column(String(64), nullable=False, default="ANY")
    session_bucket: Mapped[str] = mapped_column(String(32), nullable=False, default="ANY")
    volatility_bucket: Mapped[str] = mapped_column(String(32), nullable=False, default="ANY")
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_r: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    expectancy: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    suspended: Mapped[bool] = mapped_column(nullable=False, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class SymbolProfile(Base, WorkspaceOwnedMixin, TimestampMixin):
    __tablename__ = "symbol_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)


class CalibrationBin(Base, WorkspaceOwnedMixin, TimestampMixin):
    __tablename__ = "calibration_bins"
    __table_args__ = (
        UniqueConstraint("workspace_id", "bin_lower", "bin_upper", name="uq_calibration_bin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin_lower: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    bin_upper: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    predicted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    realized_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

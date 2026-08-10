from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import WorkspaceOwnedMixin


class EpisodeSource(StrEnum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"


class AgentEpisode(Base, WorkspaceOwnedMixin):
    __tablename__ = "agent_episodes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    timeframes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    regime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volatility_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    r_achieved: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    evidence_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[EpisodeSource] = mapped_column(
        String(16), nullable=False, default=EpisodeSource.LIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )


class MemoryType(StrEnum):
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"
    LESSON = "LESSON"
    USER = "USER"


class AgentMemory(Base, WorkspaceOwnedMixin):
    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    memory_type: Mapped[MemoryType] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    sample_size: Mapped[int] = mapped_column(nullable=False, default=0)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    freshness_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    low_sample: Mapped[bool] = mapped_column(nullable=False, default=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    derived_from_episode_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )


class MemoryEmbedding(Base, WorkspaceOwnedMixin):
    __tablename__ = "memory_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    model: Mapped[str] = mapped_column(
        String(128), nullable=False, default="text-embedding-3-small"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )


class Lesson(Base, WorkspaceOwnedMixin):
    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    supporting_episode_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    decay_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_edited: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import WorkspaceOwnedMixin


class NewsEvent(Base):
    __tablename__ = "news_events"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_news_events_source_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    relevance: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    market_impact: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )


class ResearchItem(Base, WorkspaceOwnedMixin):
    __tablename__ = "research_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    items_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    contradictions_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

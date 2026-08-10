from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.mixins import WorkspaceOwnedMixin


class JournalEntry(Base, TimestampMixin, WorkspaceOwnedMixin):
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lesson: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    promoted_to_lesson_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

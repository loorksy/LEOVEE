"""The prompt catalogue: every system prompt text the platform has ever sent.

Platform-global on purpose, and listed in the RLS allowlist for that reason.
Prompts are platform assets, identical for every tenant, and a per-workspace
copy of the same text would fragment exactly the grouping the learning loop
needs — "how did runs under this prompt perform" is a question about the prompt,
not about a workspace.

Nothing tenant-derived is stored here: the body is a file from the repository,
and the hash is a function of that file.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

__all__ = ["PromptVersion"]


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    #: The content hash IS the identity: two deploys shipping the same text are
    #: the same version, whatever the file was named in between.
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.0.0")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

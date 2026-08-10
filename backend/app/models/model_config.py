from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ModelConfig(Base):
    __tablename__ = "model_configs"
    __table_args__ = (UniqueConstraint("task", name="uq_model_configs_task"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_model: Mapped[str] = mapped_column(String(128), nullable=False)
    fallback_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fallback_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import PlanCode


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[PlanCode] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    limits_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    features_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_billing_webhook_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

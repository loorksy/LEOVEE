from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import RecommendationDirection, TradeStatus
from app.models.mixins import WorkspaceOwnedMixin


class Trade(Base, TimestampMixin, WorkspaceOwnedMixin):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    direction: Mapped[RecommendationDirection] = mapped_column(
        Enum(RecommendationDirection, name="trade_direction"),
        nullable=False,
    )
    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus, name="trade_status"),
        nullable=False,
        default=TradeStatus.IDEA,
    )
    entry: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    targets_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    oanda_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

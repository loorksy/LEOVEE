"""One remembered moment on the shared candle store, and how it resolved.

Deliberately carries **no** tenant columns. A case is a fact about XAUUSD —
identical for every workspace, computed once, shared — in the same class as
`candles`, `structures` and `price_zones`. What is *not* shared is
`strategy_stats`: how a given workspace's own plans performed is that
workspace's record and nothing else's.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

__all__ = ["MarketCase"]


class MarketCase(Base):
    __tablename__ = "market_cases"
    __table_args__ = (
        UniqueConstraint("symbol_id", "timeframe", "case_ts", name="uq_market_case_moment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    case_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    regime: Mapped[str] = mapped_column(String(16), nullable=False)
    trend: Mapped[str] = mapped_column(String(8), nullable=False)
    range_zone: Mapped[str] = mapped_column(String(16), nullable=False)
    pullback_depth: Mapped[float] = mapped_column(Float, nullable=False)
    impulse_atr: Mapped[float] = mapped_column(Float, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, nullable=False)
    session: Mapped[str] = mapped_column(String(8), nullable=False)
    structure_run: Mapped[int] = mapped_column(Integer, nullable=False)

    atr: Mapped[float] = mapped_column(Float, nullable=False)
    entry: Mapped[float] = mapped_column(Float, nullable=False)

    buy_resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)
    buy_bars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buy_net_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_mfe_atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_mae_atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sell_bars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sell_net_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_mfe_atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_mae_atr: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: The 8 fingerprint slots, for cheap candidate recall only. The ranking
    #: metric is weighted L1 in process — see `cases/fingerprint.py`.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

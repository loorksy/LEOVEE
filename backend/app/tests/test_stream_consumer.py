from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.candle import Candle
from app.services.market.candle_aggregator import PriceTick
from app.services.market.stream_consumer import OandaCandleStreamConsumer
from app.services.market.stream_manager import OandaStreamManager


class _FakeStreamManager(OandaStreamManager):
    def __init__(self) -> None:
        settings = Settings(OANDA_API_TOKEN="token", OANDA_ACCOUNT_ID="acct")
        super().__init__(settings, ["EURUSD"])
        self._pending_ticks: list[PriceTick] = []

    def queue_tick(self, tick: PriceTick) -> None:
        self._pending_ticks.append(tick)

    async def ticks_with_fallback(self) -> AsyncIterator[PriceTick]:
        for tick in self._pending_ticks:
            yield tick


@pytest.mark.asyncio
async def test_stream_consumer_persists_completed_candles(db_session: AsyncSession) -> None:
    settings = Settings(OANDA_API_TOKEN="token", OANDA_ACCOUNT_ID="acct")
    manager = _FakeStreamManager()
    t0 = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 12, 1, 10, tzinfo=UTC)
    manager.queue_tick(PriceTick("EURUSD", Decimal("1.1"), Decimal("1.1002"), t0))
    manager.queue_tick(PriceTick("EURUSD", Decimal("1.2"), Decimal("1.2002"), t1))

    consumer = OandaCandleStreamConsumer(settings, ["EURUSD"], stream_manager=manager)
    stats = await consumer.run_cycle(db_session, max_ticks=2)
    assert stats["ticks_seen"] == 2
    assert stats["candles_persisted"] >= 1
    rows = await db_session.execute(select(Candle))
    assert len(rows.scalars().all()) >= 1

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.providers.market.base import NormalizedCandle
from app.services.market.candle_aggregator import PriceTick
from app.services.market.gaps import assert_gapless_series
from app.services.market.stream_consumer import OandaCandleStreamConsumer
from app.services.market.stream_manager import OandaStreamManager


class _ReconnectStreamManager(OandaStreamManager):
    """Simulates stream reconnect with REST backfill (HTTP mock on _rest)."""

    def __init__(
        self,
        *,
        backfill_candles: list[NormalizedCandle],
        tick: PriceTick,
        partial_tick: PriceTick | None = None,
    ) -> None:
        settings = Settings(OANDA_API_TOKEN="token", OANDA_ACCOUNT_ID="acct")
        super().__init__(settings, ["XAUUSD"])
        self._backfill_candles = backfill_candles
        self._pending_ticks = [t for t in (partial_tick, tick) if t is not None]
        self._rest.fetch_candles = AsyncMock(return_value=backfill_candles)  # type: ignore[method-assign]
        self._last_tick_ts[tick.symbol] = tick.ts - timedelta(minutes=5)

    async def ticks_with_fallback(self) -> AsyncIterator[PriceTick]:
        self._connected = True
        for pending in self._pending_ticks:
            yield pending

    async def backfill_gaps(self, symbol: str) -> list[datetime]:
        tick_ts = self._pending_ticks[-1].ts
        return [tick_ts - timedelta(minutes=2), tick_ts - timedelta(minutes=1)]


@pytest.mark.asyncio
async def test_stream_disconnect_fallback_backfill_gapless_series(db_session: AsyncSession) -> None:
    """
    §99: reconnect → REST backfill; no gaps, no duplicate buckets; boundary partial candle.
    """
    settings = Settings(OANDA_API_TOKEN="token", OANDA_ACCOUNT_ID="acct")
    anchor = datetime(2026, 3, 1, 12, 5, 10, tzinfo=UTC)
    partial_ts = anchor - timedelta(seconds=30)
    partial = PriceTick("XAUUSD", Decimal("1.0950"), Decimal("1.0952"), partial_ts)
    tick = PriceTick("XAUUSD", Decimal("1.1000"), Decimal("1.1002"), anchor)

    backfill: list[NormalizedCandle] = []
    for i in range(4):
        ts = anchor.replace(minute=1) - timedelta(minutes=3 - i)
        price = Decimal("1.09") + Decimal(i) * Decimal("0.001")
        backfill.append(
            NormalizedCandle(
                symbol="XAUUSD",
                timeframe=Timeframe.M1,
                ts=ts,
                open=price,
                high=price + Decimal("0.0002"),
                low=price - Decimal("0.0002"),
                close=price,
                volume=Decimal("0"),
                complete=True,
                source="oanda_rest_mock",
            )
        )

    backfill.append(
        NormalizedCandle(
            symbol="XAUUSD",
            timeframe=Timeframe.M1,
            ts=anchor.replace(minute=4, second=0, microsecond=0),
            open=Decimal("1.099"),
            high=Decimal("1.0995"),
            low=Decimal("1.0985"),
            close=Decimal("1.0992"),
            volume=Decimal("0"),
            complete=False,
            source="oanda_rest_mock_boundary",
        )
    )

    manager = _ReconnectStreamManager(backfill_candles=backfill, tick=tick, partial_tick=partial)
    consumer = OandaCandleStreamConsumer(settings, ["XAUUSD"], stream_manager=manager)
    stats = await consumer.run_cycle(db_session, max_ticks=2)

    assert stats["backfill_rows"] >= len(backfill)

    rows = await db_session.execute(
        select(Candle).where(Candle.timeframe == Timeframe.M1).order_by(Candle.ts.asc())
    )
    candles = list(rows.scalars().all())
    backfill_rows = sorted(
        [c for c in candles if c.source == "oanda_rest_mock"],
        key=lambda c: c.ts,
    )
    assert len(backfill_rows) >= 4
    assert assert_gapless_series(backfill_rows[:4], timeframe=Timeframe.M1)

    distinct_buckets = await db_session.scalar(
        select(func.count(func.distinct(Candle.ts))).where(Candle.timeframe == Timeframe.M1)
    )
    assert distinct_buckets == len(candles)

    boundary_rows = [c for c in candles if c.source == "oanda_rest_mock_boundary"]
    if boundary_rows:
        assert boundary_rows[0].complete is False

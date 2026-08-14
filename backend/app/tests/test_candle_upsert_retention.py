from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle
from app.models.enums import Timeframe
from app.providers.market.base import NormalizedCandle
from app.services import market_data
from app.services.market.gaps import detect_candle_gaps, repair_candle_gaps
from app.services.market.retention import purge_stale_candles
from app.tests.doubles.market import FakeMarketDataProvider


def _candle(ts: datetime, close: str) -> NormalizedCandle:
    price = Decimal(close)
    return NormalizedCandle(
        symbol="XAUUSD",
        timeframe=Timeframe.M1,
        ts=ts,
        open=price,
        high=price + Decimal("0.0001"),
        low=price - Decimal("0.0001"),
        close=price,
        volume=Decimal("0"),
        complete=True,
        source="test",
    )


@pytest.mark.asyncio
async def test_upsert_duplicate_updates_row(db_session: AsyncSession) -> None:
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    first = _candle(t0, "1.1000")
    second = _candle(t0, "1.2000")
    await market_data.upsert_candles(db_session, symbol.id, [first])
    await market_data.upsert_candles(db_session, symbol.id, [second])
    count = await db_session.scalar(select(func.count()).select_from(Candle))
    assert count == 1
    row = await db_session.scalar(select(Candle).where(Candle.ts == t0))
    assert row is not None
    assert row.close == Decimal("1.2000")


@pytest.mark.asyncio
async def test_upsert_out_of_order_preserves_extremes(db_session: AsyncSession) -> None:
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    base = _candle(t0, "1.1000")
    await market_data.upsert_candles(db_session, symbol.id, [base])
    late_update = NormalizedCandle(
        symbol="XAUUSD",
        timeframe=Timeframe.M1,
        ts=t0,
        open=Decimal("1.1000"),
        high=Decimal("1.2500"),
        low=Decimal("1.0500"),
        close=Decimal("1.1100"),
        volume=Decimal("0"),
        complete=True,
        source="test",
    )
    await market_data.upsert_candles(db_session, symbol.id, [late_update])
    row = await db_session.scalar(select(Candle).where(Candle.ts == t0))
    assert row is not None
    assert row.high == Decimal("1.2500")
    assert row.low == Decimal("1.0500")


@pytest.mark.asyncio
async def test_gap_detection_and_repair(db_session: AsyncSession) -> None:
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    await market_data.upsert_candles(
        db_session,
        symbol.id,
        [_candle(t0, "1.10"), _candle(t0 + timedelta(minutes=2), "1.12")],
    )
    stored = await market_data.load_recent_candles(
        db_session, symbol.id, timeframe=Timeframe.M1, count=10
    )
    gaps = detect_candle_gaps(stored, timeframe=Timeframe.M1)
    assert len(gaps) == 1
    assert gaps[0] == t0 + timedelta(minutes=1)

    fill = _candle(t0 + timedelta(minutes=1), "1.11")
    provider = FakeMarketDataProvider([fill])
    repaired = await repair_candle_gaps(
        db_session,
        symbol_code="XAUUSD",
        timeframe=Timeframe.M1,
        provider=provider,
    )
    assert repaired >= 1
    stored_after = await market_data.load_recent_candles(
        db_session, symbol.id, timeframe=Timeframe.M1, count=10
    )
    assert len(stored_after) == 3


@pytest.mark.asyncio
async def test_retention_job_deletes_stale_candles(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("CANDLE_RETENTION_M1_DAYS", "7")
    get_settings.cache_clear()
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    old = _candle(datetime(2020, 1, 1, 12, 0, tzinfo=UTC), "1.05")
    fresh = _candle(datetime.now(UTC).replace(second=0, microsecond=0), "1.10")
    await market_data.upsert_candles(db_session, symbol.id, [old, fresh])
    deleted = await purge_stale_candles(db_session, timeframe=Timeframe.M1)
    assert deleted >= 1
    remaining = await db_session.scalar(select(func.count()).select_from(Candle))
    assert remaining == 1
    get_settings.cache_clear()

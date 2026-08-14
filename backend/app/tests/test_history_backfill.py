"""A year of shared history, filled resumably."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeframes import ACTIVE_TIMEFRAMES
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.providers.market.base import NormalizedCandle
from app.services.market.history import HISTORY_DAYS, backfill_all, backfill_timeframe
from app.tests.doubles.market import FakeMarketDataProvider

START = datetime(2026, 1, 1, tzinfo=UTC)


def _series(
    count: int,
    *,
    timeframe: Timeframe = Timeframe.M15,
    step_minutes: int = 15,
    complete: bool = True,
) -> list[NormalizedCandle]:
    candles: list[NormalizedCandle] = []
    for i in range(count):
        price = Decimal("2000") + Decimal(i) * Decimal("0.10")
        candles.append(
            NormalizedCandle(
                symbol="XAUUSD",
                timeframe=timeframe,
                ts=START + timedelta(minutes=step_minutes * i),
                open=price,
                high=price + Decimal("0.50"),
                low=price - Decimal("0.50"),
                close=price + Decimal("0.20"),
                volume=Decimal("100"),
                complete=complete,
                source="test_double",
            )
        )
    return candles


async def _stored(session: AsyncSession, timeframe: Timeframe) -> int:
    total = await session.scalar(
        select(func.count()).select_from(Candle).where(Candle.timeframe == timeframe)
    )
    return int(total or 0)


async def test_backfill_stores_the_series(db_session: AsyncSession) -> None:
    provider = FakeMarketDataProvider(_series(120))
    written = await backfill_timeframe(
        db_session,
        symbol_code="XAUUSD",
        timeframe=Timeframe.M15,
        provider=provider,
        now=START + timedelta(days=2),
    )
    await db_session.commit()
    # `written` counts upserts, and the boundary candle is deliberately
    # re-requested on each page in case it was incomplete when first stored, so
    # it can exceed the distinct row count. Rows stored is the invariant.
    assert written >= 120
    assert await _stored(db_session, Timeframe.M15) == 120


async def test_backfill_is_idempotent(db_session: AsyncSession) -> None:
    """A second run must not duplicate rows — it upserts on (symbol, tf, ts)."""
    provider = FakeMarketDataProvider(_series(50))
    for _ in range(2):
        await backfill_timeframe(
            db_session,
            symbol_code="XAUUSD",
            timeframe=Timeframe.M15,
            provider=provider,
            now=START + timedelta(days=2),
        )
        await db_session.commit()
    assert await _stored(db_session, Timeframe.M15) == 50


async def test_backfill_resumes_from_the_newest_stored_candle(
    db_session: AsyncSession,
) -> None:
    """The first run fills history; later runs cost one page, not a year."""
    first_half = _series(30)
    await backfill_timeframe(
        db_session,
        symbol_code="XAUUSD",
        timeframe=Timeframe.M15,
        provider=FakeMarketDataProvider(first_half),
        now=START + timedelta(days=2),
    )
    await db_session.commit()

    full = _series(60)
    written = await backfill_timeframe(
        db_session,
        symbol_code="XAUUSD",
        timeframe=Timeframe.M15,
        provider=FakeMarketDataProvider(full),
        now=START + timedelta(days=2),
    )
    await db_session.commit()
    # Only the new candles plus the resumed boundary one, not all sixty.
    assert written < 60
    assert await _stored(db_session, Timeframe.M15) == 60


async def test_incomplete_candles_are_not_stored(db_session: AsyncSession) -> None:
    """The forming candle belongs to the live stream, which writes it on close."""
    provider = FakeMarketDataProvider(_series(20, complete=False))
    written = await backfill_timeframe(
        db_session,
        symbol_code="XAUUSD",
        timeframe=Timeframe.M15,
        provider=provider,
        now=START + timedelta(days=2),
    )
    await db_session.commit()
    assert written == 0


async def test_backfill_terminates_when_the_provider_stops_advancing(
    db_session: AsyncSession,
) -> None:
    """A provider that keeps returning the same page must not loop forever."""
    provider = FakeMarketDataProvider(_series(5))
    await backfill_timeframe(
        db_session,
        symbol_code="XAUUSD",
        timeframe=Timeframe.M15,
        provider=provider,
        now=START + timedelta(days=365),
    )
    await db_session.commit()
    assert await _stored(db_session, Timeframe.M15) == 5


async def test_backfill_all_covers_every_active_timeframe(
    db_session: AsyncSession,
) -> None:
    provider = FakeMarketDataProvider(_series(10))
    results = await backfill_all(db_session, symbol_code="XAUUSD", provider=provider, days=30)
    await db_session.commit()
    assert set(results) == {tf.value for tf in ACTIVE_TIMEFRAMES}


async def test_unknown_symbols_are_refused(db_session: AsyncSession) -> None:
    from app.core.symbols import UnknownSymbolError

    with pytest.raises(UnknownSymbolError):
        await backfill_timeframe(
            db_session,
            symbol_code="EURUSD",
            timeframe=Timeframe.M15,
            provider=FakeMarketDataProvider(_series(5)),
        )


@pytest.mark.no_db
def test_history_window_is_a_full_year() -> None:
    # A year covers a full seasonal cycle, so a pattern recalled in March has
    # last March to compare against.
    assert HISTORY_DAYS == 365


@pytest.mark.no_db
def test_retention_keeps_at_least_the_history_window() -> None:
    """Purging inside the analysis window would silently degrade the engines."""
    from app.core.config import get_settings

    settings = get_settings()
    retention = {
        Timeframe.M1: settings.candle_retention_m1_days,
        Timeframe.M5: settings.candle_retention_m5_days,
        Timeframe.M15: settings.candle_retention_m15_days,
        Timeframe.H1: settings.candle_retention_h1_days,
        Timeframe.H4: settings.candle_retention_h4_days,
    }
    for timeframe in ACTIVE_TIMEFRAMES:
        assert retention[timeframe] >= HISTORY_DAYS, (
            f"{timeframe.value} retention is shorter than the history window"
        )

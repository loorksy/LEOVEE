from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.candle import Candle
from app.models.enums import Timeframe


def retention_cutoff_for_timeframe(
    timeframe: Timeframe,
    *,
    now: datetime | None = None,
) -> datetime:
    settings = get_settings()
    now = now or datetime.now(UTC)
    days_map = {
        Timeframe.M1: settings.candle_retention_m1_days,
        Timeframe.M5: settings.candle_retention_m5_days,
        Timeframe.M15: settings.candle_retention_m15_days,
        Timeframe.M30: settings.candle_retention_m30_days,
        Timeframe.H1: settings.candle_retention_h1_days,
        Timeframe.H4: settings.candle_retention_h4_days,
        Timeframe.D1: settings.candle_retention_d1_days,
    }
    days = days_map.get(timeframe, settings.candle_retention_h1_days)
    return now - timedelta(days=days)


async def purge_stale_candles(
    session: AsyncSession,
    *,
    timeframe: Timeframe | None = None,
    now: datetime | None = None,
) -> int:
    """Delete candles older than configured retention for each timeframe."""
    total = 0
    timeframes = [timeframe] if timeframe else list(Timeframe)
    for tf in timeframes:
        cutoff = retention_cutoff_for_timeframe(tf, now=now)
        result = await session.execute(
            delete(Candle).where(Candle.timeframe == tf, Candle.ts < cutoff)
        )
        cursor = cast(CursorResult[Any], result)
        total += int(cursor.rowcount or 0)
    await session.flush()
    return total

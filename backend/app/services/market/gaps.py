from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle
from app.models.enums import Timeframe
from app.providers.market.base import MarketDataProvider, NormalizedCandle
from app.services import market_data


def timeframe_to_minutes(timeframe: Timeframe) -> int:
    mapping = {
        Timeframe.M1: 1,
        Timeframe.M5: 5,
        Timeframe.M15: 15,
        Timeframe.M30: 30,
        Timeframe.H1: 60,
        Timeframe.H4: 240,
        Timeframe.D1: 1440,
    }
    return mapping[timeframe]


def detect_candle_gaps(
    candles: list[Candle],
    *,
    timeframe: Timeframe,
) -> list[datetime]:
    """Return missing bucket start timestamps between first and last stored candle."""
    if len(candles) < 2:
        return []
    ordered = sorted(candles, key=lambda c: c.ts)
    step = timedelta(minutes=timeframe_to_minutes(timeframe))
    gaps: list[datetime] = []
    for prev, curr in zip(ordered, ordered[1:], strict=False):
        expected = prev.ts + step
        while expected < curr.ts:
            gaps.append(expected)
            expected += step
    return gaps


async def load_candles_for_symbol(
    session: AsyncSession,
    symbol_id: uuid.UUID,
    timeframe: Timeframe,
    *,
    limit: int = 5000,
) -> list[Candle]:
    result = await session.execute(
        select(Candle)
        .where(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
        .order_by(Candle.ts.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def repair_candle_gaps(
    session: AsyncSession,
    *,
    symbol_code: str,
    timeframe: Timeframe,
    provider: MarketDataProvider,
    max_fill: int = 500,
) -> int:
    """
    Detect gaps in stored candles and fill via REST provider (idempotent upsert).
  """
    symbol = await market_data.get_or_create_symbol(session, symbol_code)
    stored = await load_candles_for_symbol(session, symbol.id, timeframe)
    gaps = detect_candle_gaps(stored, timeframe=timeframe)
    if not gaps:
        return 0

    granularity = timeframe.value
    normalized = await provider.fetch_candles(
        symbol_code,
        granularity=granularity,
        count=min(len(gaps) + 5, max_fill),
    )
    if not normalized:
        return 0

    gap_set = {g.replace(microsecond=0) for g in gaps}
    to_upsert: list[NormalizedCandle] = []
    for candle in normalized:
        ts = candle.ts if candle.ts.tzinfo else candle.ts.replace(tzinfo=UTC)
        bucket = ts.replace(second=0, microsecond=0)
        if bucket in gap_set:
            to_upsert.append(candle)

    if not to_upsert and normalized:
        to_upsert = normalized

    return await market_data.upsert_candles(session, symbol.id, to_upsert)


def assert_gapless_series(
    candles: list[Candle],
    *,
    timeframe: Timeframe,
) -> bool:
    """True when consecutive candles are exactly one timeframe apart."""
    if len(candles) < 2:
        return True
    step = timedelta(minutes=timeframe_to_minutes(timeframe))
    ordered = sorted(candles, key=lambda c: c.ts)
    return all(
        curr.ts - prev.ts == step for prev, curr in zip(ordered, ordered[1:], strict=False)
    )

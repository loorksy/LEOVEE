from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle
from app.models.enums import Timeframe
from app.models.symbol import Symbol
from app.providers.market.base import NormalizedCandle
from app.providers.market.oanda import OandaMarketDataProvider, get_market_provider


async def get_or_create_symbol(session: AsyncSession, code: str) -> Symbol:
    normalized = code.replace("_", "").upper()
    existing = await session.scalar(select(Symbol).where(Symbol.code == normalized))
    if existing is not None:
        return existing
    base = normalized[:3]
    quote = normalized[3:]
    symbol = Symbol(
        code=normalized,
        base_currency=base,
        quote_currency=quote,
        provider_mappings_json={"oanda": f"{base}_{quote}"},
    )
    session.add(symbol)
    await session.flush()
    return symbol


async def upsert_candles(
    session: AsyncSession,
    symbol_id: uuid.UUID,
    candles: list[NormalizedCandle],
) -> int:
    if not candles:
        return 0
    inserted = 0
    for candle in candles:
        stmt = (
            insert(Candle)
            .values(
                symbol_id=symbol_id,
                timeframe=candle.timeframe,
                ts=candle.ts,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                complete=candle.complete,
                source=candle.source,
                ingested_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["symbol_id", "timeframe", "ts"],
                set_={
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "complete": candle.complete,
                    "source": candle.source,
                    "ingested_at": datetime.now(UTC),
                },
            )
        )
        await session.execute(stmt)
        inserted += 1
    await session.flush()
    return inserted


async def fetch_and_store_candles(
    session: AsyncSession,
    *,
    symbol_code: str,
    timeframe: Timeframe,
    count: int = 100,
    provider: OandaMarketDataProvider | None = None,
) -> tuple[Symbol, list[Candle]]:
    granularity = timeframe.value
    market = provider or get_market_provider()
    normalized = await market.fetch_candles(symbol_code, granularity=granularity, count=count)
    symbol = await get_or_create_symbol(session, symbol_code)
    await upsert_candles(session, symbol.id, normalized)
    result = await session.execute(
        select(Candle)
        .where(Candle.symbol_id == symbol.id, Candle.timeframe == timeframe)
        .order_by(Candle.ts.desc())
        .limit(count)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return symbol, rows


def candle_to_dict(candle: Candle) -> dict[str, str | float | bool]:
    return {
        "ts": candle.ts.isoformat(),
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": float(candle.volume) if candle.volume is not None else 0.0,
        "complete": candle.complete,
    }

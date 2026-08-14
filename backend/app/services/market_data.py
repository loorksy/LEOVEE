from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.symbols import require_instrument
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.models.symbol import Symbol
from app.providers.market.base import MarketDataProvider, NormalizedCandle
from app.providers.market.oanda import get_market_provider


async def get_or_create_symbol(session: AsyncSession, code: str) -> Symbol:
    """Resolve a symbol row, refusing anything outside the allowlist.

    This is the single chokepoint (app/core/symbols.py). It raises rather than
    substituting the default: a caller asking for an instrument the platform
    does not analyse has made a mistake, and silently answering about gold
    instead would produce a confident analysis of the wrong market.

    Currency and pip metadata come from the instrument spec rather than being
    sliced out of the ticker — `normalized[:3]` happens to work for XAUUSD but
    would give the wrong pip location for every JPY pair, and a wrong pip
    location scales stop distances and position sizes by a hundred without
    failing anywhere visible.
    """
    spec = require_instrument(code)
    existing = await session.scalar(select(Symbol).where(Symbol.code == spec.symbol))
    if existing is not None:
        return existing
    symbol = Symbol(
        code=spec.symbol,
        base_currency=spec.base,
        quote_currency=spec.quote,
        asset_class=spec.asset_class,
        pip_location=spec.pip_location,
        provider_mappings_json={"oanda": spec.oanda_instrument},
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
    provider: MarketDataProvider | None = None,
) -> tuple[Symbol, list[Candle]]:
    # Allowlist BEFORE the outbound call, not after. The chokepoint has to sit
    # in front of the network request: fetching first placed a raw, unvalidated
    # symbol into the OANDA URL path with the platform's credentials, and only
    # then rejected it — the gate has to gate the thing it guards.
    spec = require_instrument(symbol_code)
    granularity = timeframe.value
    market = provider or get_market_provider()
    normalized = await market.fetch_candles(spec.symbol, granularity=granularity, count=count)
    symbol = await get_or_create_symbol(session, spec.symbol)
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


async def load_recent_candles(
    session: AsyncSession,
    symbol_id: uuid.UUID,
    *,
    timeframe: Timeframe,
    count: int = 100,
) -> list[Candle]:
    result = await session.execute(
        select(Candle)
        .where(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
        .order_by(Candle.ts.desc())
        .limit(count)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def load_oldest_candle(
    session: AsyncSession,
    symbol_id: uuid.UUID,
    *,
    timeframe: Timeframe,
) -> Candle | None:
    """The earliest stored candle — how far back the history actually reaches.

    The agent needs this to tell a thin store from a quiet market: "no structure
    before this point" and "we only have two days of data" look identical
    otherwise.
    """
    result = await session.execute(
        select(Candle)
        .where(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
        .order_by(Candle.ts.asc())
        .limit(1)
    )
    return result.scalars().first()


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

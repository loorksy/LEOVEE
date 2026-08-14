"""Backfill and maintain a full year of candles, for every active timeframe.

The candle store is **shared by every workspace**. Gold's M15 candles are the
same candles for all of them, so they are fetched once and read by all — the
`candles` table deliberately carries no tenant columns, and
`app/tests/conformance/test_rls_coverage.py` records that as a decision rather
than an omission. Per-workspace candle copies would multiply storage by the
tenant count and produce identical rows.

**A year, not a page.** Analysis was previously fed whatever a single REST call
returned. A year of history is what makes the rest of the platform possible:
the geometry engine needs a long window to find structure, similar-case memory
needs history to have analogues in, and calibration needs enough closed
outcomes to say anything. On M1 that is roughly 360,000 candles for gold —
OANDA caps a request at 5,000, so the window is walked in pages.

The walk is **resumable by construction**: each page starts from the last
timestamp already stored, so an interrupted backfill continues where it stopped
rather than refetching a year, and a scheduled run costs one page once the
history is complete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.symbols import require_instrument
from app.core.timeframes import ACTIVE_TIMEFRAMES
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.providers.market.base import MAX_CANDLES_PER_REQUEST, MarketDataProvider
from app.services import market_data

logger = structlog.get_logger(__name__)

__all__ = ["HISTORY_DAYS", "TIMEFRAME_MINUTES", "backfill_timeframe", "backfill_all"]

#: How much history the platform keeps warm. One year is the shortest span that
#: covers a full seasonal cycle, so a pattern the agent recalls in March has
#: last March to compare against.
HISTORY_DAYS = 365

TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
}

#: A backfill that has not reached the present after this many pages is stopped
#: and resumed on the next run. Without a bound, a provider that keeps
#: returning the same page would spin forever.
MAX_PAGES_PER_RUN = 200


async def _latest_stored(
    session: AsyncSession, symbol_id: uuid.UUID, timeframe: Timeframe
) -> datetime | None:
    latest = await session.scalar(
        select(func.max(Candle.ts)).where(
            Candle.symbol_id == symbol_id, Candle.timeframe == timeframe
        )
    )
    return latest if isinstance(latest, datetime) else None


async def backfill_timeframe(
    session: AsyncSession,
    *,
    symbol_code: str,
    timeframe: Timeframe,
    provider: MarketDataProvider,
    days: int = HISTORY_DAYS,
    now: datetime | None = None,
) -> int:
    """Fill this timeframe forward to the present. Returns candles written."""
    spec = require_instrument(symbol_code)
    symbol = await market_data.get_or_create_symbol(session, spec.symbol)
    moment = now or datetime.now(UTC)
    horizon = moment - timedelta(days=days)

    latest = await _latest_stored(session, symbol.id, timeframe)
    # Resume from the last stored candle, or start at the horizon on a cold
    # store. Re-requesting the last candle is intentional: it may have been
    # incomplete when stored, and the upsert corrects it.
    cursor = max(latest, horizon) if latest is not None else horizon

    written = 0
    for _ in range(MAX_PAGES_PER_RUN):
        page = await provider.fetch_candles_from(
            spec.oanda_instrument,
            granularity=timeframe.value,
            start=cursor,
            count=MAX_CANDLES_PER_REQUEST,
        )
        if not page:
            break

        # Only completed candles are stored. The forming one changes every tick
        # and belongs to the live stream, which writes it when it closes.
        complete = [candle for candle in page if candle.complete]
        if complete:
            written += await market_data.upsert_candles(session, symbol.id, complete)

        newest = max(candle.ts for candle in page)
        if newest <= cursor:
            # No forward progress: the provider has nothing newer, so the
            # history is current.
            break
        cursor = newest
        if cursor >= moment:
            break

    if written:
        logger.info(
            "candle_backfill_progress",
            symbol=spec.symbol,
            timeframe=timeframe.value,
            written=written,
        )
    return written


async def backfill_all(
    session: AsyncSession,
    *,
    symbol_code: str,
    provider: MarketDataProvider,
    days: int = HISTORY_DAYS,
) -> dict[str, int]:
    """Bring every active timeframe up to date.

    Slowest first: H4 is a few hundred candles a year and completes in one
    page, so the context frames are usable almost immediately while M1 — three
    orders of magnitude larger — is still filling.
    """
    results: dict[str, int] = {}
    for timeframe in sorted(ACTIVE_TIMEFRAMES, key=lambda tf: TIMEFRAME_MINUTES[tf], reverse=True):
        results[timeframe.value] = await backfill_timeframe(
            session,
            symbol_code=symbol_code,
            timeframe=timeframe,
            provider=provider,
            days=days,
        )
    return results

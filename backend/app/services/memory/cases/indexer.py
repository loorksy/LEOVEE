"""Sweep the shared candle store into market-case memory.

Case memory answers "when has gold looked like this before, and what came
next" — but only if something writes it. `build_cases`/`store_cases` had no
runtime caller, so in production `market_cases` stayed empty forever and the
`find_similar_cases` / `get_case_outcome_stats` tools always returned nothing.
This is that caller: a bounded, idempotent nightly sweep.

**Bounded.** Fingerprinting a full year of M1 (~half a million bars) every
night would wedge the worker, so each timeframe is capped at the most recent
``CASE_INDEX_MAX_BARS``. On M15 — the primary decision frame — that covers most
of a year; on M1 it is a recent window, which is what a scalp similarity read
actually consults.

**Idempotent.** ``store_cases`` upserts by moment, so re-running the sweep over
an overlapping window rewrites the same rows rather than duplicating them.

**Platform-global.** ``market_cases`` carries no tenant columns and no RLS (it
is shared market fact, like ``candles``), so the sweep runs on the ordinary
runtime session with no workspace binding — and must never be fed a
workspace's own record.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.symbols import TRADABLE_SYMBOLS
from app.core.timeframes import DECISION_TIMEFRAMES
from app.engines.bar import bars_from_candles
from app.services import market_data
from app.services.memory.cases.store import build_cases, store_cases

logger = structlog.get_logger(__name__)

#: The most-recent bars fingerprinted per timeframe per sweep. A ceiling on
#: worker time, not a statement about how much history matters: on the slower
#: decision frames this is most of the stored year; on M1 it is a recent window.
CASE_INDEX_MAX_BARS = 50_000


async def index_market_cases(session: AsyncSession) -> dict[str, int]:
    """Index every tradable symbol across the decision frames. Returns rows written per key."""
    written: dict[str, int] = {}
    for symbol_code in TRADABLE_SYMBOLS:
        symbol = await market_data.get_or_create_symbol(session, symbol_code)
        for timeframe in DECISION_TIMEFRAMES:
            candles = await market_data.load_recent_candles(
                session, symbol.id, timeframe=timeframe, count=CASE_INDEX_MAX_BARS
            )
            bars = bars_from_candles(candles)
            cases = build_cases(bars)
            count = await store_cases(
                session, cases, symbol_id=symbol.id, timeframe=timeframe.value
            )
            await session.commit()
            written[f"{symbol_code}:{timeframe.value}"] = count
            logger.info(
                "market_cases_indexed",
                symbol=symbol_code,
                timeframe=timeframe.value,
                bars=len(bars),
                cases=count,
            )
    return written

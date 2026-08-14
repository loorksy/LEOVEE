"""The live price feed: always connected, writing candles as they close.

A cron that wakes every fifteen minutes and reads five hundred ticks is not a
live feed. Between wakes the platform is blind, and a scalp decided on M1 needs
the current candle, not one from up to fifteen minutes ago.

So the stream is a **supervised long-running task** started with the worker. It
holds the OANDA pricing connection open, aggregates ticks into candles, and
persists each one the moment it closes. When the connection drops it reconnects
with exponential backoff and jitter, and the gap it left behind is repaired from
REST by the backfill job — the stream owns "now", the backfill owns "what we
missed".

It is supervised rather than fire-and-forget because the failure mode of a
crashed stream is silence: no error surfaces, the candles simply stop, and the
agent carries on analysing stale data. The supervisor restarts it and logs each
restart so the silence becomes visible.
"""

from __future__ import annotations

import asyncio
import random

import structlog

from app.core.symbols import TRADABLE_SYMBOLS
from app.infrastructure.database import get_session_factory

logger = structlog.get_logger(__name__)

__all__ = ["run_stream_forever", "start_stream_supervisor"]

#: Ticks to drain before committing and looping. Small enough that a completed
#: candle reaches the database promptly, large enough to avoid a commit per tick.
BATCH_TICKS = 200

_MIN_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 60.0


async def run_stream_forever(*, batch_ticks: int = BATCH_TICKS) -> None:
    """Consume the pricing stream until cancelled, reconnecting on failure."""
    from app.services.market.stream_consumer import run_market_stream_cycle

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")

    backoff = _MIN_BACKOFF_SECONDS
    while True:
        try:
            async with factory() as session:
                stats = await run_market_stream_cycle(
                    session,
                    instruments=list(TRADABLE_SYMBOLS),
                    max_ticks=batch_ticks,
                )
                await session.commit()
            if stats.get("candles_persisted"):
                logger.info("stream_candles_persisted", **stats)
            # A clean cycle resets the backoff; otherwise a single blip would
            # leave the feed throttled long after it recovered.
            backoff = _MIN_BACKOFF_SECONDS
        except asyncio.CancelledError:
            logger.info("stream_runner_cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 — the feed must outlive any error
            logger.warning("stream_cycle_failed", error=str(exc), retry_in=backoff)
            # Jitter keeps every replica from reconnecting in lockstep after a
            # provider-side outage.
            await asyncio.sleep(backoff + random.uniform(0, backoff * 0.5))
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)


def start_stream_supervisor(*, batch_ticks: int = BATCH_TICKS) -> asyncio.Task[None]:
    """Run the feed as a background task, restarting it if it ever returns."""

    async def _supervise() -> None:
        while True:
            try:
                await run_stream_forever(batch_ticks=batch_ticks)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # run_stream_forever handles its own retries, so reaching here
                # means something structural failed. Log loudly: a silent
                # stream looks exactly like a quiet market.
                logger.error("stream_supervisor_restart", error=str(exc))
                await asyncio.sleep(_MAX_BACKOFF_SECONDS)

    return asyncio.create_task(_supervise(), name="oanda-stream")

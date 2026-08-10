from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.infrastructure.database import get_session_factory
from app.services.learning.outcome_recorder import TerminalOutcome
from app.services.learning.pipeline import run_learning_pipeline


async def process_learning_outcome(ctx: dict[str, object], payload: dict[str, object]) -> str:
    """Arq job: run deterministic learning pipeline for a terminal outcome payload."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    terminal = TerminalOutcome(**payload)  # type: ignore[arg-type]
    async with factory() as session:
        await run_learning_pipeline(session, terminal)
        await session.commit()
    return "learning_pipeline_ok"


async def oanda_stream_consumer_job(_ctx: dict[str, object]) -> str:
    """Arq job: OANDA pricing stream -> aggregated M1 candles -> DB + realtime fan-out."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    from app.services.market.stream_consumer import run_market_stream_cycle

    async with factory() as session:
        stats = await run_market_stream_cycle(session, max_ticks=500)
        await session.commit()
    return f"oanda_stream_ok:{stats}"


async def candle_backfill_job(_ctx: dict[str, object]) -> str:
    """Scheduled gap repair for M1 candles (REST via configured OANDA provider)."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    from app.models.enums import Timeframe
    from app.providers.market.oanda import get_market_provider
    from app.services.market.gaps import repair_candle_gaps

    provider = get_market_provider()
    repaired = 0
    async with factory() as session:
        for symbol in ("EURUSD", "GBPUSD", "USDJPY"):
            repaired += await repair_candle_gaps(
                session,
                symbol_code=symbol,
                timeframe=Timeframe.M1,
                provider=provider,
            )
        await session.commit()
    return f"candle_backfill_ok:{repaired}"


async def candle_retention_job(_ctx: dict[str, object]) -> str:
    """Purge candles older than per-timeframe retention policy."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    from app.services.market.retention import purge_stale_candles

    async with factory() as session:
        deleted = await purge_stale_candles(session)
        await session.commit()
    return f"candle_retention_ok:{deleted}"


async def news_ingestion_job(_ctx: dict[str, object]) -> str:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    from app.providers.news.finnhub import get_news_provider
    from app.services.news_service import ingest_news_from_provider

    try:
        provider = get_news_provider()
    except Exception as exc:
        return f"news_ingestion_skipped:{type(exc).__name__}"

    async with factory() as session:
        count = await ingest_news_from_provider(session, provider, currency="USD")
        await session.commit()
    return f"news_ingestion_ok:{count}"


async def memory_embedding_index_job(_ctx: dict[str, object]) -> str:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    from sqlalchemy import select

    from app.models.memory import AgentMemory, MemoryEmbedding
    from app.services.memory_service import index_memory_embedding

    indexed = 0
    async with factory() as session:
        rows = await session.execute(
            select(AgentMemory).where(~AgentMemory.id.in_(select(MemoryEmbedding.memory_id)))
        )
        for mem in rows.scalars().all():
            text = f"{mem.key}:{mem.content_json}"
            await index_memory_embedding(
                session,
                tenant_id=mem.tenant_id,
                workspace_id=mem.workspace_id,
                memory_id=mem.id,
                text=text,
            )
            indexed += 1
        await session.commit()
    return f"memory_embedding_index_ok:{indexed}"


async def memory_decay_job(_ctx: dict[str, object]) -> str:
    """Placeholder for memory aging sweeps (invoked on schedule)."""
    return "memory_decay_ok"


async def thesis_monitor_job(_ctx: dict[str, object]) -> str:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    from app.services.thesis_monitor_worker import run_thesis_monitor_cycle

    async with factory() as session:
        outcomes = await run_thesis_monitor_cycle(session)
        await session.commit()
    changed = sum(1 for o in outcomes if o.get("changed"))
    return f"thesis_monitor_ok:{changed}"


class WorkerSettings:
    functions = [
        process_learning_outcome,
        oanda_stream_consumer_job,
        candle_backfill_job,
        candle_retention_job,
        news_ingestion_job,
        memory_embedding_index_job,
        thesis_monitor_job,
        memory_decay_job,
    ]
    cron_jobs = [
        cron(oanda_stream_consumer_job, minute={0, 15, 30, 45}),  # type: ignore[arg-type]
        cron(candle_backfill_job, hour={0}, minute=5),  # type: ignore[arg-type]
        cron(candle_retention_job, hour={1}, minute=15),  # type: ignore[arg-type]
        cron(news_ingestion_job, hour={2}, minute=0),  # type: ignore[arg-type]
        cron(thesis_monitor_job, minute={5, 35}),  # type: ignore[arg-type]
        cron(memory_decay_job, hour={3}, minute=30),  # type: ignore[arg-type]
    ]

    @staticmethod
    def redis_settings() -> RedisSettings:
        settings = get_settings()
        url = settings.redis_url or "redis://localhost:6379/0"
        return RedisSettings.from_dsn(url)

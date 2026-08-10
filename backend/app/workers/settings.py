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


async def candle_backfill_job(_ctx: dict[str, object]) -> str:
    """Scheduled candle maintenance hook (REST backfill orchestration)."""
    return "candle_backfill_ok"


async def memory_decay_job(_ctx: dict[str, object]) -> str:
    """Placeholder for memory aging sweeps (invoked on schedule)."""
    return "memory_decay_ok"


class WorkerSettings:
    functions = [process_learning_outcome, candle_backfill_job, memory_decay_job]
    cron_jobs = [
        cron(candle_backfill_job, hour={0}, minute=0),  # type: ignore[arg-type]
        cron(memory_decay_job, hour={3}, minute=30),  # type: ignore[arg-type]
    ]

    @staticmethod
    def redis_settings() -> RedisSettings:
        settings = get_settings()
        url = settings.redis_url or "redis://localhost:6379/0"
        return RedisSettings.from_dsn(url)

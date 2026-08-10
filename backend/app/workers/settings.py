from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings


async def placeholder_candle_backfill(_ctx: dict[str, object]) -> str:
    return "candle_backfill_ok"


async def placeholder_memory_decay(_ctx: dict[str, object]) -> str:
    return "memory_decay_ok"


class WorkerSettings:
    functions = [placeholder_candle_backfill, placeholder_memory_decay]
    cron_jobs = [
        cron(placeholder_candle_backfill, hour={0}, minute=0),  # type: ignore[arg-type]
    ]

    @staticmethod
    def redis_settings() -> RedisSettings:
        settings = get_settings()
        url = settings.redis_url or "redis://localhost:6379/0"
        return RedisSettings.from_dsn(url)

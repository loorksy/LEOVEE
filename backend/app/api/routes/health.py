from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

router = APIRouter(tags=["health"])


async def _check_redis(redis_url: str) -> tuple[bool, str | None]:
    client: Redis[str] | None = None
    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        pong = await client.ping()
        return bool(pong), None
    except Exception as exc:  # noqa: BLE001 — health probe
        return False, str(exc)
    finally:
        if client is not None:
            await client.close()


async def _check_database(database_url: str) -> tuple[bool, str | None]:
    engine: AsyncEngine | None = None
    try:
        engine = create_async_engine(database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 — health probe
        return False, str(exc)
    finally:
        if engine is not None:
            await engine.dispose()


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, Any] = {}
    healthy = True

    if settings.database_url:
        ok, err = await _check_database(settings.database_url)
        checks["database"] = {"ok": ok, "error": err}
        healthy = healthy and ok
    else:
        checks["database"] = {"ok": True, "skipped": True}

    if settings.redis_url:
        ok, err = await _check_redis(settings.redis_url)
        checks["redis"] = {"ok": ok, "error": err}
        healthy = healthy and ok
    else:
        checks["redis"] = {"ok": True, "skipped": True}

    return {"status": "ok" if healthy else "degraded", "checks": checks}


@router.get("/health/startup")
async def startup() -> dict[str, str]:
    return {"status": "ok", "migrations": "pending"}

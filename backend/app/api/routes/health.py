from typing import Any

import structlog
from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.database import get_engine

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)

# `/health/ready` is unauthenticated (it is a load-balancer probe), so the
# failure reason is logged server-side rather than returned: a raw exception
# string can carry a DSN, a hostname, or driver internals to anyone who curls it.
_UNAVAILABLE = "unavailable"


async def _check_redis(redis_url: str) -> tuple[bool, str | None]:
    client: Redis[str] | None = None
    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        pong = await client.ping()
        return bool(pong), None
    except Exception as exc:  # noqa: BLE001 — health probe
        logger.warning("health_redis_check_failed", error=str(exc))
        return False, _UNAVAILABLE
    finally:
        if client is not None:
            await client.close()


async def _check_database() -> tuple[bool, str | None]:
    engine = get_engine()
    if engine is None:
        return False, "not_configured"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 — health probe
        logger.warning("health_database_check_failed", error=str(exc))
        return False, _UNAVAILABLE


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, Any] = {}
    healthy = True

    if settings.database_url:
        ok, err = await _check_database()
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
    """Kubernetes startup probe — migrations run via `scripts/migrate.sh` job before roll."""
    return {
        "status": "ok",
        "migrations": "external-job",
        "hint": "Run scripts/migrate.sh or docker compose run --rm migrate",
    }

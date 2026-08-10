#!/usr/bin/env bash
# Enqueue a one-shot Arq job on the staging stack (stream consumer / worker proof).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

JOB="${1:-oanda_stream_consumer_job}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.agent.yml"

docker compose ${COMPOSE_FILES} exec -T worker python - <<PY
import asyncio
from arq import create_pool
from arq.connections import RedisSettings
from app.core.config import get_settings
from app.workers import settings as worker_settings

async def main() -> None:
    redis = RedisSettings.from_dsn(get_settings().redis_url or "redis://redis:6379/0")
    pool = await create_pool(redis)
    job = await pool.enqueue_job("${JOB}")
    print("enqueued", job.job_id if job else None)
    await pool.close()

asyncio.run(main())
PY

echo "[worker] waiting for job result (redis arq)…"
sleep 15
docker compose ${COMPOSE_FILES} logs worker --tail 30

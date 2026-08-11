#!/usr/bin/env bash
# Disposable VPS staging deploy (DEPLOYMENT.md §16.1). OANDA practice only; isolated DB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. GitHub Actions uploads it from secrets before deploy." >&2
  exit 1
fi

# Broker policy — refuse before touching containers.
if ! grep -qE '^OANDA_ENVIRONMENT=practice$' .env; then
  echo "ERROR: OANDA_ENVIRONMENT must be practice in .env — refusing deploy." >&2
  exit 1
fi
if grep -qiE '^OANDA_EXECUTION=(1|true|yes|on|enabled)$' .env; then
  echo "ERROR: OANDA_EXECUTION enabled in .env — refusing deploy." >&2
  exit 1
fi

export ENVIRONMENT="${ENVIRONMENT:-staging}"

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.staging.yml"
if [[ -f docker-compose.agent.yml ]]; then
  COMPOSE_FILES="${COMPOSE_FILES} -f docker-compose.agent.yml"
fi

compose() {
  # shellcheck disable=SC2086
  docker compose ${COMPOSE_FILES} "$@"
}

dump_logs() {
  local svc="$1"
  echo "========== last 120 lines: ${svc} =========="
  compose logs --no-color --tail 120 "${svc}" || true
}

fail_service() {
  local svc="$1"
  local why="$2"
  echo "ERROR: ${svc} unhealthy — ${why}" >&2
  dump_logs "${svc}"
  exit 1
}

echo "[deploy] running migrations (alembic upgrade head via migration role)…"
compose run --rm --build migrate

echo "[deploy] starting postgres redis api worker web caddy (stream consumer runs in worker)…"
compose up -d --build postgres redis api worker web caddy

echo "[deploy] waiting for container health…"
for _ in $(seq 1 60); do
  api_ok=0
  worker_ok=0
  web_ok=0
  if curl -fsS "http://127.0.0.1:8000/health/live" >/dev/null 2>&1; then
    api_ok=1
  fi
  if compose ps --status running worker 2>/dev/null | grep -q worker; then
    worker_ok=1
  fi
  # Web is behind Caddy on staging (18080) or direct nginx in the web container.
  if curl -fsS "http://127.0.0.1:18080/" >/dev/null 2>&1 \
    || compose exec -T web wget -q -O- http://127.0.0.1/ >/dev/null 2>&1; then
    web_ok=1
  fi
  if [[ "${api_ok}" -eq 1 && "${worker_ok}" -eq 1 && "${web_ok}" -eq 1 ]]; then
    break
  fi
  sleep 2
done

echo "[deploy] verifying api…"
curl -fsS "http://127.0.0.1:8000/health/live" | grep -q '"status":"ok"' \
  || fail_service api "GET /health/live failed"
curl -fsS "http://127.0.0.1:8000/health/ready" | grep -q '"status"' \
  || fail_service api "GET /health/ready failed"

echo "[deploy] verifying worker (hosts OANDA stream consumer cron)…"
compose ps worker 2>/dev/null | grep -qiE 'running|up' \
  || fail_service worker "container not running"
# Stream consumer is scheduled inside the Arq worker — prove the job is registered.
compose exec -T worker python - <<'PY' || fail_service worker "stream consumer import failed"
from app.workers.settings import WorkerSettings, oanda_stream_consumer_job

assert callable(oanda_stream_consumer_job)
assert oanda_stream_consumer_job in WorkerSettings.functions
print("stream_consumer_ok")
PY

echo "[deploy] verifying web…"
if ! curl -fsS "http://127.0.0.1:18080/" >/dev/null 2>&1; then
  compose exec -T web wget -q -O- http://127.0.0.1/ >/dev/null 2>&1 \
    || fail_service web "HTTP check failed (caddy :18080 and web container)"
fi

echo "[deploy] smoke checks…"
API_URL="${API_URL:-http://127.0.0.1:8000}" "${ROOT}/scripts/smoke_staging.sh" \
  || fail_service api "smoke_staging.sh failed"

DEPLOYED_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "[deploy] staging stack is up"
echo "[deploy] DEPLOYED_COMMIT_SHA=${DEPLOYED_SHA}"
echo "[deploy] tear-down: docker compose ${COMPOSE_FILES} down -v"

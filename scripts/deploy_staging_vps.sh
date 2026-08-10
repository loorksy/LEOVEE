#!/usr/bin/env bash
# Disposable VPS staging deploy (DEPLOYMENT.md §16.1). OANDA practice only; isolated DB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and configure staging secrets before deploy." >&2
  exit 1
fi

export ENVIRONMENT="${ENVIRONMENT:-staging}"

echo "[deploy] running migrations (one-shot)…"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.staging.yml"
if [ -f docker-compose.agent.yml ]; then
  COMPOSE_FILES="${COMPOSE_FILES} -f docker-compose.agent.yml"
fi
docker compose ${COMPOSE_FILES} run --rm migrate

echo "[deploy] starting api, worker, web…"
docker compose ${COMPOSE_FILES} up -d --build api worker web

echo "[deploy] waiting for API health…"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:8000/health/live" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

API_URL="${API_URL:-http://127.0.0.1:8000}" "${ROOT}/scripts/smoke_staging.sh"
echo "[deploy] staging stack is up. Tear-down: docker compose ${COMPOSE_FILES} down -v"

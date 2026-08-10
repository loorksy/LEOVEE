#!/usr/bin/env bash
# Logical backup via the running compose Postgres service (includes pgvector).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.agent.yml"
BACKUP_DIR="${BACKUP_DIR:-${ROOT}/backups}"
BACKUP_PATH="${BACKUP_PATH:-${BACKUP_DIR}/leovee-$(date -u +%Y%m%dT%H%M%SZ).dump}"
mkdir -p "$(dirname "${BACKUP_PATH}")"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[backup] dry-run: docker compose ${COMPOSE_FILES} exec -T postgres pg_dump -Fc -U leovee -d leovee > ${BACKUP_PATH}"
  exit 0
fi

docker compose ${COMPOSE_FILES} exec -T postgres \
  pg_dump -Fc -U leovee -d leovee >"${BACKUP_PATH}"
echo "[backup] wrote ${BACKUP_PATH}"

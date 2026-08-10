#!/usr/bin/env bash
# Restore backup into a scratch database inside the compose Postgres container.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.agent.yml"
BACKUP_FILE="${1:?Usage: restore_pg_compose.sh <backup.dump> [scratch_db_name]}"
SCRATCH_DB="${2:-leovee_restore_test}"

if [[ "${BACKUP_FILE}" == "--dry-run" ]]; then
  echo "[restore] dry-run: create ${SCRATCH_DB}, pg_restore into scratch DB"
  exit 0
fi

docker compose ${COMPOSE_FILES} exec -T postgres psql -U leovee -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${SCRATCH_DB}' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS ${SCRATCH_DB};" \
  -c "CREATE DATABASE ${SCRATCH_DB} OWNER leovee;"

docker compose ${COMPOSE_FILES} exec -T postgres \
  pg_restore --clean --if-exists -U leovee -d "${SCRATCH_DB}" <"${BACKUP_FILE}"

docker compose ${COMPOSE_FILES} exec -T postgres psql -U leovee -d "${SCRATCH_DB}" -v ON_ERROR_STOP=1 \
  -c "SELECT extname FROM pg_extension WHERE extname = 'vector';" \
  -c "SELECT COUNT(*) AS alembic_versions FROM alembic_version;"

echo "[restore] verified scratch database ${SCRATCH_DB}"

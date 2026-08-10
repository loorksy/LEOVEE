#!/usr/bin/env bash
# Run Alembic migrations (use DATABASE_MIGRATION_URL — superuser/migration role).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/backend"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[migrate] dry-run: would execute 'alembic upgrade head' in ${ROOT}/backend"
  echo "[migrate] requires DATABASE_MIGRATION_URL"
  exit 0
fi

if [[ -z "${DATABASE_MIGRATION_URL:-}" ]]; then
  echo "DATABASE_MIGRATION_URL is required" >&2
  exit 1
fi

export DATABASE_MIGRATION_URL
alembic upgrade head
echo "[migrate] alembic upgrade head completed"

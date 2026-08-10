#!/usr/bin/env bash
# Restore from pg_dump custom-format backup. Target must be empty or dedicated DR instance.
set -euo pipefail

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[restore] dry-run: would run pg_restore --clean --if-exists -d PGDATABASE BACKUP_FILE"
  exit 0
fi

BACKUP_FILE="${1:?Usage: restore_pg.sh <backup.dump>}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-leovee}"
PGDATABASE="${PGDATABASE:-leovee}"
export PGPASSWORD="${PGPASSWORD:-leovee}"

pg_restore --clean --if-exists -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" "${BACKUP_FILE}"
echo "[restore] completed into ${PGDATABASE}"

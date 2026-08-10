#!/usr/bin/env bash
# PostgreSQL logical backup (custom format). Use with cron + object storage in production.
set -euo pipefail

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[backup] dry-run: would run pg_dump -Fc to BACKUP_PATH"
  echo "[backup] requires PGHOST PGUSER PGPASSWORD PGDATABASE (or DATABASE_URL parse)"
  exit 0
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_PATH="${BACKUP_PATH:-${BACKUP_DIR}/leovee-$(date -u +%Y%m%dT%H%M%SZ).dump}"

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-leovee}"
PGDATABASE="${PGDATABASE:-leovee}"

mkdir -p "$(dirname "${BACKUP_PATH}")"
export PGPASSWORD="${PGPASSWORD:-leovee}"

pg_dump -Fc -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -f "${BACKUP_PATH}"
echo "[backup] wrote ${BACKUP_PATH}"

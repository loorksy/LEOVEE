#!/usr/bin/env bash
# Remote VPS deploy over SSH (DEPLOYMENT.md §16.1).
# Usage: VPS_HOST=72.60.83.140 VPS_USER=root ./scripts/remote_deploy_vps.sh
set -euo pipefail

VPS_HOST="${VPS_HOST:?Set VPS_HOST}"
VPS_USER="${VPS_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/leovee}"
REPO_URL="${REPO_URL:-https://github.com/loorksy/LEOVEE.git}"
BRANCH="${BRANCH:-main}"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)

if [[ -n "${VPS_SSH_PRIVATE_KEY:-}" ]]; then
  KEY_FILE="$(mktemp)"
  trap 'rm -f "${KEY_FILE}"' EXIT
  printf '%s\n' "${VPS_SSH_PRIVATE_KEY}" >"${KEY_FILE}"
  chmod 600 "${KEY_FILE}"
  SSH_OPTS+=(-i "${KEY_FILE}")
elif [[ -n "${VPS_SSH_KEY_PATH:-}" && -f "${VPS_SSH_KEY_PATH}" ]]; then
  SSH_OPTS+=(-i "${VPS_SSH_KEY_PATH}")
fi

echo "[remote] ensuring ${REMOTE_DIR} on ${VPS_USER}@${VPS_HOST}"
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" "mkdir -p ${REMOTE_DIR}"

echo "[remote] syncing repository (git pull)…"
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" bash -s <<EOF
set -euo pipefail
if [ ! -d ${REMOTE_DIR}/.git ]; then
  git clone ${REPO_URL} ${REMOTE_DIR}
fi
cd ${REMOTE_DIR}
git fetch origin ${BRANCH}
git checkout ${BRANCH}
git pull origin ${BRANCH}
test -f .env || cp .env.example .env
export ENVIRONMENT=staging
./scripts/deploy_staging_vps.sh
EOF

echo "[remote] deploy finished. Smoke from laptop: API_URL=http://${VPS_HOST}:8000 ./scripts/smoke_staging.sh"

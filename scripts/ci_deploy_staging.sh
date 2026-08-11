#!/usr/bin/env bash
# GitHub Actions → VPS staging deploy.
# Expects secrets already validated by the workflow. Never echoes secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

VPS_HOST="${VPS_HOST:?}"
VPS_USER="${VPS_USER:-root}"
VPS_SSH_KEY_PATH="${VPS_SSH_KEY_PATH:?}"
REMOTE_DIR="${REMOTE_DIR:-/opt/leovee}"
REF="${REF:?Set REF to branch or tag}"
REPO_SLUG="${REPO_SLUG:-loorksy/LEOVEE}"
GH_TOKEN="${GH_TOKEN:?}"

SSH_OPTS=(
  -i "${VPS_SSH_KEY_PATH}"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=30
)

ssh_vps() {
  ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" "$@"
}

scp_vps() {
  scp "${SSH_OPTS[@]}" "$@"
}

echo "[ci-deploy] generating staging .env (values masked in Actions)"
ENV_FILE="$(mktemp)"
DEPLOY_ENV="$(mktemp)"
trap 'rm -f "${ENV_FILE}" "${DEPLOY_ENV}"' EXIT
chmod +x "${ROOT}/scripts/generate_staging_env.sh"
"${ROOT}/scripts/generate_staging_env.sh" "${ENV_FILE}"

umask 077
cat >"${DEPLOY_ENV}" <<EOF
REF=${REF}
REMOTE_DIR=${REMOTE_DIR}
REPO_SLUG=${REPO_SLUG}
GH_TOKEN=${GH_TOKEN}
EOF
chmod 600 "${DEPLOY_ENV}"

echo "[ci-deploy] ensuring ${REMOTE_DIR} on ${VPS_USER}@${VPS_HOST}"
ssh_vps "mkdir -p '${REMOTE_DIR}/.deploy'"

echo "[ci-deploy] uploading deploy context + staging .env (held until after git sync)"
scp_vps "${DEPLOY_ENV}" "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/.deploy/pull.env"
scp_vps "${ENV_FILE}" "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/.deploy/staging.env"
ssh_vps "chmod 600 '${REMOTE_DIR}/.deploy/pull.env' '${REMOTE_DIR}/.deploy/staging.env'"

echo "[ci-deploy] syncing ${REF} and deploying"
ssh_vps bash -s <<'REMOTE'
set -euo pipefail
set +x

set -a
# shellcheck disable=SC1091
source /opt/leovee/.deploy/pull.env
set +a
rm -f /opt/leovee/.deploy/pull.env

mkdir -p "${REMOTE_DIR}"
cd "${REMOTE_DIR}"

if [[ ! -d .git ]]; then
  # Directory may already contain .deploy/ — init instead of clone into non-empty dir.
  git init
  git remote add origin "https://x-access-token:${GH_TOKEN}@github.com/${REPO_SLUG}.git" || \
    git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${REPO_SLUG}.git"
else
  git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${REPO_SLUG}.git"
fi

git fetch --force origin "${REF}"
git checkout --force FETCH_HEAD
git remote set-url origin "https://github.com/${REPO_SLUG}.git"
unset GH_TOKEN

# Install runtime .env after checkout so it is never overwritten by git.
cp -f .deploy/staging.env .env
chmod 600 .env
rm -f .deploy/staging.env

if ! grep -qE '^OANDA_ENVIRONMENT=practice$' .env; then
  echo "ERROR: .env OANDA_ENVIRONMENT is not practice — refusing deploy"
  exit 1
fi
if grep -qiE '^OANDA_EXECUTION=(1|true|yes|on|enabled)$' .env; then
  echo "ERROR: .env enables OANDA_EXECUTION — refusing deploy"
  exit 1
fi

export ENVIRONMENT=staging
chmod +x scripts/*.sh
./scripts/deploy_staging_vps.sh

DEPLOYED_SHA="$(git rev-parse HEAD)"
echo "[ci-deploy] DEPLOYED_COMMIT_SHA=${DEPLOYED_SHA}"
echo "${DEPLOYED_SHA}" >.deploy/last_sha
REMOTE

echo "[ci-deploy] remote deploy finished"
echo -n "[ci-deploy] deployed commit: "
ssh_vps "cat '${REMOTE_DIR}/.deploy/last_sha'"

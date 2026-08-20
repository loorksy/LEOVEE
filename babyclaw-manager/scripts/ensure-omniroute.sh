#!/usr/bin/env bash
# Start local OmniRoute gateway on 127.0.0.1:20128 if it is not running.
set -euo pipefail

NAME="${OMNIROUTE_CONTAINER:-omniroute}"
IMAGE="${OMNIROUTE_IMAGE:-diegosouzapw/omniroute:latest}"
ENV_FILE="${1:-/opt/leovee/omniroute.env}"
BABY_ENV="${2:-/home/babyclaw/.env}"

mkdir -p "$(dirname "${ENV_FILE}")"
: > "${ENV_FILE}"
if [[ -f "${BABY_ENV}" ]]; then
  grep -E '^(OPENAI_API_KEY|ANTHROPIC_API_KEY)=' "${BABY_ENV}" >> "${ENV_FILE}" || true
fi

if docker inspect -f '{{.State.Running}}' "${NAME}" 2>/dev/null | grep -q true; then
  echo "omniroute already running"
  exit 0
fi

if docker inspect "${NAME}" >/dev/null 2>&1; then
  docker start "${NAME}"
  echo "omniroute started"
  exit 0
fi

touch "${ENV_FILE}"
docker pull "${IMAGE}"
docker run -d --name "${NAME}" --restart unless-stopped --stop-timeout 40 \
  --env-file "${ENV_FILE}" \
  -p 127.0.0.1:20128:20128 \
  -v omniroute-data:/app/data \
  "${IMAGE}"
echo "omniroute created on 127.0.0.1:20128"

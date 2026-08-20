#!/usr/bin/env bash
# Start or refresh the local OmniRoute gateway on 127.0.0.1:20128.
# Recreates the container when OpenAI/Anthropic keys in omniroute.env change.
set -euo pipefail

NAME="${OMNIROUTE_CONTAINER:-omniroute}"
IMAGE="${OMNIROUTE_IMAGE:-diegosouzapw/omniroute:latest}"
ENV_FILE="${1:-/opt/leovee/omniroute.env}"
BABY_ENV="${2:-/home/babyclaw/.env}"
HASH_FILE="${ENV_FILE}.applied"

mkdir -p "$(dirname "${ENV_FILE}")"
umask 077
touch "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

upsert_env() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp
  tmp="$(mktemp)"
  python3 - "$file" "$key" "$value" "$tmp" <<'PY'
import sys
path, key, value, tmp = sys.argv[1:5]
try:
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
except FileNotFoundError:
    lines = []
found = False
out = []
prefix = key + "="
for line in lines:
    if line.startswith(prefix):
        out.append(prefix + value)
        found = True
    else:
        out.append(line)
if not found:
    out.append(prefix + value)
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out).rstrip() + "\n")
PY
  mv "${tmp}" "${file}"
  chmod 600 "${file}"
}

read_env_value() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import sys
path, key = sys.argv[1:3]
prefix = key + "="
try:
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(prefix):
                value = line[len(prefix):].rstrip("\n")
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                print(value, end="")
                break
except FileNotFoundError:
    pass
PY
}

if ! grep -qE '^INITIAL_PASSWORD=' "${ENV_FILE}"; then
  upsert_env "${ENV_FILE}" "INITIAL_PASSWORD" "$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)"
fi
if ! grep -qE '^JWT_SECRET=' "${ENV_FILE}"; then
  upsert_env "${ENV_FILE}" "JWT_SECRET" "$(openssl rand -base64 48)"
fi
if ! grep -qE '^API_KEY_SECRET=' "${ENV_FILE}"; then
  upsert_env "${ENV_FILE}" "API_KEY_SECRET" "$(openssl rand -hex 32)"
fi
if ! grep -qE '^STORAGE_ENCRYPTION_KEY=' "${ENV_FILE}"; then
  upsert_env "${ENV_FILE}" "STORAGE_ENCRYPTION_KEY" "$(openssl rand -hex 32)"
fi
upsert_env "${ENV_FILE}" "PORT" "20128"
upsert_env "${ENV_FILE}" "REQUIRE_API_KEY" "false"

if [[ -f "${BABY_ENV}" ]]; then
  openai_key="$(read_env_value "${BABY_ENV}" "OPENAI_API_KEY")"
  anthropic_key="$(read_env_value "${BABY_ENV}" "ANTHROPIC_API_KEY")"
  if [[ -n "${openai_key}" ]]; then
    upsert_env "${ENV_FILE}" "OPENAI_API_KEY" "${openai_key}"
  fi
  if [[ -n "${anthropic_key}" ]]; then
    upsert_env "${ENV_FILE}" "ANTHROPIC_API_KEY" "${anthropic_key}"
  fi
fi

new_hash="$(sha256sum "${ENV_FILE}" | awk '{print $1}')"
old_hash=""
if [[ -f "${HASH_FILE}" ]]; then
  old_hash="$(tr -d '[:space:]' < "${HASH_FILE}")"
fi

running="false"
if docker inspect -f '{{.State.Running}}' "${NAME}" 2>/dev/null | grep -q true; then
  running="true"
fi

if [[ "${running}" == "true" && "${new_hash}" == "${old_hash}" ]]; then
  echo "omniroute already running"
  exit 0
fi

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  docker pull "${IMAGE}"
fi

if docker inspect "${NAME}" >/dev/null 2>&1; then
  docker rm -f "${NAME}" >/dev/null
fi

docker run -d --name "${NAME}" --restart unless-stopped --stop-timeout 40 \
  --env-file "${ENV_FILE}" \
  -p 127.0.0.1:20128:20128 \
  -v omniroute-data:/app/data \
  "${IMAGE}" >/dev/null

echo "${new_hash}" > "${HASH_FILE}"
chmod 600 "${HASH_FILE}"

for _ in $(seq 1 45); do
  if curl -sf "http://127.0.0.1:20128/api/monitoring/health" >/dev/null 2>&1 \
    || curl -sf "http://127.0.0.1:20128/health" >/dev/null 2>&1; then
    echo "omniroute ready on 127.0.0.1:20128"
    exit 0
  fi
  sleep 2
done

echo "omniroute started on 127.0.0.1:20128 (health still warming)"

#!/usr/bin/env bash
# Post-deploy smoke checks (staging / VPS). Set API_URL to the reachable API base.
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
API_URL="${API_URL%/}"

echo "[smoke] live ${API_URL}/health/live"
curl -fsS "${API_URL}/health/live" | grep -q '"status":"ok"'

echo "[smoke] ready ${API_URL}/health/ready"
curl -fsS "${API_URL}/health/ready" | grep -q '"status"'

echo "[smoke] startup ${API_URL}/health/startup"
curl -fsS "${API_URL}/health/startup" | grep -q '"status":"ok"'

echo "[smoke] metrics ${API_URL}/metrics"
# Staging/production require METRICS_BEARER_TOKEN. Prefer authenticated check when set;
# otherwise accept a gated 401/503 as healthy (endpoint is up and refusing anonymous scrapes).
METRICS_TOKEN="${METRICS_BEARER_TOKEN:-}"
if [[ -z "${METRICS_TOKEN}" && -f .env ]]; then
  METRICS_TOKEN="$(grep -E '^METRICS_BEARER_TOKEN=' .env | head -1 | cut -d= -f2- || true)"
fi
if [[ -n "${METRICS_TOKEN}" ]]; then
  curl -fsS -H "Authorization: Bearer ${METRICS_TOKEN}" "${API_URL}/metrics" | head -n 3 >/dev/null
  echo "[smoke] metrics authenticated OK"
else
  code="$(curl -sS -o /tmp/leovee-metrics.body -w '%{http_code}' "${API_URL}/metrics" || true)"
  if [[ "${code}" == "200" ]]; then
    head -n 3 /tmp/leovee-metrics.body
  elif [[ "${code}" == "401" || "${code}" == "503" ]]; then
    echo "[smoke] metrics gated (${code}) — OK for staging without anonymous scrapes"
  else
    echo "ERROR: unexpected /metrics status ${code}" >&2
    head -n 20 /tmp/leovee-metrics.body >&2 || true
    exit 1
  fi
fi

echo "[smoke] all checks passed"

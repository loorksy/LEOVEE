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
curl -fsS "${API_URL}/metrics" | head -n 3

echo "[smoke] all checks passed"

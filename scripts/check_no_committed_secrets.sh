#!/usr/bin/env bash
# Fail CI if likely secrets are committed (not exhaustive; complements review).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if git ls-files --error-unmatch .env .env.local .env.production 2>/dev/null; then
  echo "ERROR: .env file must not be committed"
  exit 1
fi

PATTERNS=(
  'sk-[A-Za-z0-9]{20,}'
  'AKIA[0-9A-Z]{16}'
  'BEGIN (RSA |OPENSSH )?PRIVATE KEY'
  'api-fxtrade\.oanda\.com'
)

FOUND=0
for pattern in "${PATTERNS[@]}"; do
  if git grep -E "$pattern" -- ':!scripts/check_no_committed_secrets.sh' ':!*.md' ':!backend/app/core/config.py' 2>/dev/null; then
    FOUND=1
  fi
done

if [[ "$FOUND" -ne 0 ]]; then
  echo "ERROR: suspected secret or live OANDA host in tracked files"
  exit 1
fi

echo "check_no_committed_secrets: ok"

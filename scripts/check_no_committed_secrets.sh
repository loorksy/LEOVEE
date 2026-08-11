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
  'sk-ant-[A-Za-z0-9_-]{20,}'
  'AKIA[0-9A-Z]{16}'
  'BEGIN (RSA |OPENSSH )?PRIVATE KEY'
  'api-fxtrade\.oanda\.com'
  'OANDA_API_TOKEN[[:space:]]*=[[:space:]]*['\''"]?[A-Za-z0-9_-]{40,}'
)

FOUND=0
for pattern in "${PATTERNS[@]}"; do
  # Print only file:line with redacted body — never echo secret values into CI logs.
  if matches=$(git grep -n -E "$pattern" -- \
    ':!scripts/check_no_committed_secrets.sh' \
    ':!scripts/check_no_secret_leaks.sh' \
    ':!*.md' \
    ':!backend/app/core/config.py' \
    2>/dev/null); then
    echo "$matches" | sed -E 's/^([^:]+:[0-9]+):.*/\1: [REDACTED]/'
    FOUND=1
  fi
done

if [[ "$FOUND" -ne 0 ]]; then
  echo "ERROR: suspected secret or live OANDA host in tracked files"
  exit 1
fi

# Broader working-tree + log scan (excludes .env*)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/check_no_secret_leaks.sh"

echo "check_no_committed_secrets: ok"

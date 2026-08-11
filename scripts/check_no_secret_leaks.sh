#!/usr/bin/env bash
# Fail if token-shaped secrets appear outside .env files (tracked or working tree).
# Complements scripts/check_no_committed_secrets.sh. Never print matched secret values.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FOUND=0

# Pathspecs shared with git grep (never scan .env*).
GIT_EXCLUDES=(
  ':(exclude).env'
  ':(exclude).env.*'
  ':(exclude)**/.env'
  ':(exclude)**/.env.*'
  ':(exclude)scripts/check_no_committed_secrets.sh'
  ':(exclude)scripts/check_no_secret_leaks.sh'
  ':(exclude)**/node_modules/**'
  ':(exclude)**/__pycache__/**'
  ':(exclude)**/dist/**'
  ':(exclude)**/.venv/**'
  ':(exclude)**/venv/**'
)

# Patterns that must never appear with a real-looking secret value outside .env.
# Documentation / config host strings are handled with narrower excludes below.
SECRET_PATTERNS=(
  'OANDA_API_TOKEN[[:space:]]*=[[:space:]]*['\''"]?[A-Za-z0-9_-]{40,}'
  'Authorization:[[:space:]]*Bearer[[:space:]]+[A-Za-z0-9_-]{40,}'
  'sk-ant-[A-Za-z0-9_-]{20,}'
  'sk-[A-Za-z0-9]{20,}'
  'AKIA[0-9A-Z]{16}'
  'BEGIN (RSA |OPENSSH )?PRIVATE KEY'
)

is_env_file() {
  case "$1" in
    .env|.env.*|*/.env|*/.env.*) return 0 ;;
    *) return 1 ;;
  esac
}

report_matches() {
  local file="$1"
  local pattern="$2"
  # Redact the matched line body so secrets never land in CI logs.
  if grep -n -E "$pattern" -- "$file" >/dev/null 2>&1; then
    grep -n -E "$pattern" -- "$file" | sed -E "s|^([0-9]+):.*|${file}:\\1: [REDACTED]|"
    FOUND=1
  fi
}

for pattern in "${SECRET_PATTERNS[@]}"; do
  # Tracked files
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    report_matches "$f" "$pattern"
  done < <(git grep -l -E "$pattern" -- . "${GIT_EXCLUDES[@]}" \
    ':(exclude)*.md' \
    ':(exclude)backend/app/core/config.py' \
    2>/dev/null || true)

  # Untracked (non-ignored) files — catch local leaks before commit
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    is_env_file "$f" && continue
    case "$f" in
      scripts/check_no_committed_secrets.sh|scripts/check_no_secret_leaks.sh) continue ;;
      *.md) continue ;;
      backend/app/core/config.py) continue ;;
    esac
    [[ -f "$f" ]] || continue
    report_matches "$f" "$pattern"
  done < <(git ls-files --others --exclude-standard 2>/dev/null || true)
done

# Live OANDA REST host must not be hardcoded outside config property / docs.
LIVE_HOST='api-fxtrade\.oanda\.com'
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  report_matches "$f" "$LIVE_HOST"
done < <(git grep -l -E "$LIVE_HOST" -- . "${GIT_EXCLUDES[@]}" \
  ':(exclude)*.md' \
  ':(exclude)backend/app/core/config.py' \
  ':(exclude)scripts/check_no_committed_secrets.sh' \
  2>/dev/null || true)

# Log files under the workspace
while IFS= read -r -d '' f; do
  is_env_file "$f" && continue
  for pattern in "${SECRET_PATTERNS[@]}"; do
    report_matches "$f" "$pattern"
  done
done < <(find . -type f \( -name '*.log' -o -path '*/logs/*' \) \
  -not -path './.git/*' -not -path './node_modules/*' -print0 2>/dev/null || true)

if [[ "$FOUND" -ne 0 ]]; then
  echo "ERROR: token-shaped secret detected outside .env (values redacted)"
  exit 1
fi

echo "check_no_secret_leaks: ok"

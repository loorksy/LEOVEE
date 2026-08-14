#!/usr/bin/env bash
# The vendored TradingView library must never ship in a public repository.
#
# Its licence permits use and forbids public redistribution. Vendoring into a
# private repo is the normal arrangement (ADR 0004), but "private" is a setting
# someone can flip in a web UI months from now, with no diff and no review — and
# the moment it flips, 27 MB of licensed third-party code becomes public.
#
# So the invariant is checked by the build rather than remembered by a person.
set -euo pipefail

VENDORED="frontend/public/charting_library"
if [ ! -d "$VENDORED" ]; then
  echo "ok: no vendored charting library present"
  exit 0
fi

REPO="${GITHUB_REPOSITORY:-}"
if [ -z "$REPO" ]; then
  echo "skip: GITHUB_REPOSITORY unset, cannot determine visibility"
  exit 0
fi

# The Actions context reports it directly; fall back to the API when it does not.
VISIBILITY="${REPO_VISIBILITY:-}"
if [ -z "$VISIBILITY" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
  VISIBILITY=$(curl -fsSL \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}" 2>/dev/null \
    | sed -n 's/.*"visibility"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p' | head -1)
fi

if [ -z "$VISIBILITY" ]; then
  echo "skip: could not determine visibility for ${REPO}"
  exit 0
fi

if [ "$VISIBILITY" != "private" ]; then
  cat >&2 <<MSG
FAIL: ${REPO} is ${VISIBILITY}, and ${VENDORED} is present.

TradingView's Advanced Charts licence forbids public redistribution. Either make
the repository private again, or remove the vendored library and restore a
build-time fetch from a private source.

See frontend/vendor/tradingview/README.md and docs/adr/0004-tradingview-not-klinechart.md.
MSG
  exit 1
fi

echo "ok: ${REPO} is private; vendored library is within licence"

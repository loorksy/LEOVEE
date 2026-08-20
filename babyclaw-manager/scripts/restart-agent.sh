#!/usr/bin/env bash
# Restart the BabyClaw tmux session so a freshly written ~/.env is loaded.
set -euo pipefail

SESSION="${1:-${TMUX_SESSION:-main}}"
START_SCRIPT="${2:-${START_SCRIPT:-/home/babyclaw/start.sh}}"
USER_NAME="${3:-${BABYCLAW_USER:-babyclaw}}"

if [[ "$(id -un)" != "${USER_NAME}" ]]; then
  self="$(readlink -f "$0")"
  exec su - "${USER_NAME}" -c "$(printf '%q ' "${self}" "${SESSION}" "${START_SCRIPT}" "${USER_NAME}")"
fi

if [[ ! -f "${START_SCRIPT}" ]]; then
  echo "start script not found: ${START_SCRIPT}" >&2
  exit 1
fi

tmux kill-session -t "${SESSION}" 2>/dev/null || true
# Keep the session alive even if the bot exits immediately (missing tokens).
tmux new-session -d -s "${SESSION}" "bash '${START_SCRIPT}'; echo '[babyclaw] process exited'; exec sleep infinity"
sleep 1

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "failed to recreate tmux session ${SESSION}" >&2
  exit 1
fi

echo "restarted tmux session ${SESSION}"

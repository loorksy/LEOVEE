#!/usr/bin/env bash
# Restart the BabyClaw tmux session so a freshly written ~/.env is loaded.
set -euo pipefail

SESSION="${1:-${TMUX_SESSION:-main}}"
START_SCRIPT="${2:-${START_SCRIPT:-/home/babyclaw/start.sh}}"
USER_NAME="${3:-${BABYCLAW_USER:-babyclaw}}"

run_as_user() {
  if [[ "$(id -un)" == "${USER_NAME}" ]]; then
    bash -lc "$*"
  else
    su - "${USER_NAME}" -c "$*"
  fi
}

if [[ ! -f "${START_SCRIPT}" ]]; then
  echo "start script not found: ${START_SCRIPT}" >&2
  exit 1
fi

if run_as_user "tmux has-session -t ${SESSION} 2>/dev/null"; then
  run_as_user "tmux kill-session -t ${SESSION}"
fi

run_as_user "tmux new-session -d -s ${SESSION} 'bash ${START_SCRIPT}'"
sleep 1

if ! run_as_user "tmux has-session -t ${SESSION} 2>/dev/null"; then
  echo "failed to recreate tmux session ${SESSION}" >&2
  exit 1
fi

echo "restarted tmux session ${SESSION}"

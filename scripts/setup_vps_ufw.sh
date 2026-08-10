#!/usr/bin/env bash
# Enable host firewall: SSH + HTTP/S only (DEPLOYMENT.md §16.1).
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the VPS." >&2
  exit 1
fi

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
ufw status verbose

#!/usr/bin/env bash
# Automate Leovee removal, BabyClaw (yogesharc) install, and env-API startup.
# Run as root on the target VPS:
#   sudo CONFIRM_REMOVE_LEOVEE=yes bash setup-vps.sh
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
Usage: sudo CONFIRM_REMOVE_LEOVEE=yes bash setup-vps.sh

Environment:
  CONFIRM_REMOVE_LEOVEE=yes   required unless SKIP_LEOVEE_REMOVAL=yes
  SKIP_LEOVEE_REMOVAL=yes     skip deleting leovee.lork.cloud files
  SKIP_BABYCLAW_INSTALL=yes   skip official BabyClaw installer
  API_TOKEN                   override generated API token
  ALLOWED_IPS                 optional comma-separated IP allowlist
  LEOVEE_DOMAIN               extra domain to purge from nginx (default leovee.lork.cloud)
USAGE
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script as root on the VPS." >&2
  exit 1
fi

SKIP_LEOVEE_REMOVAL="${SKIP_LEOVEE_REMOVAL:-no}"
SKIP_BABYCLAW_INSTALL="${SKIP_BABYCLAW_INSTALL:-no}"
CONFIRM_REMOVE_LEOVEE="${CONFIRM_REMOVE_LEOVEE:-no}"
LEOVEE_DOMAIN="${LEOVEE_DOMAIN:-leovee.lork.cloud}"
API_TOKEN="FAKESECRET_k4l5m6n7o8p9q0r1s2t3"
ALLOWED_IPS="${ALLOWED_IPS:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
API_SRC="${REPO_ROOT}/api"
API_DST="/home/babyclaw/env-api"

log() { echo "[setup] $*"; }

remove_leovee() {
  if [[ "${SKIP_LEOVEE_REMOVAL}" == "yes" ]]; then
    log "Skipping Leovee removal"
    return
  fi
  if [[ "${CONFIRM_REMOVE_LEOVEE}" != "yes" ]]; then
    echo "Refusing to delete Leovee without CONFIRM_REMOVE_LEOVEE=yes" >&2
    exit 1
  fi

  log "Stopping Leovee compose stacks and containers"
  local dir
  for dir in /opt/leovee /root/leovee /var/www/leovee /srv/leovee; do
    if [[ -f "${dir}/docker-compose.yml" ]]; then
      (
        cd "${dir}"
        docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v --remove-orphans 2>/dev/null || true
        docker compose -f docker-compose.yml -f docker-compose.staging.yml down -v --remove-orphans 2>/dev/null || true
        docker compose down -v --remove-orphans 2>/dev/null || true
      )
    fi
  done

  if command -v docker >/dev/null 2>&1; then
    docker ps -a --format '{{.Names}}' | grep -Ei 'leovee' | xargs -r docker rm -f || true
    docker images --format '{{.Repository}}:{{.Tag}}' | grep -Ei 'leovee' | xargs -r docker rmi -f || true
    docker volume ls --format '{{.Name}}' | grep -Ei 'leovee' | xargs -r docker volume rm || true
  fi

  log "Removing Leovee nginx/caddy vhosts for ${LEOVEE_DOMAIN}"
  if [[ -d /etc/nginx ]]; then
    rm -f /etc/nginx/sites-enabled/*leovee* /etc/nginx/sites-available/*leovee*
    rm -f /etc/nginx/conf.d/*leovee* /etc/nginx/snippets/leovee*
    find /etc/nginx -maxdepth 3 -type f \( -name '*leovee*' -o -name "*${LEOVEE_DOMAIN}*" \) -delete 2>/dev/null || true
    if command -v nginx >/dev/null 2>&1; then
      nginx -t && systemctl reload nginx || true
    fi
  fi
  if [[ -d /etc/caddy ]]; then
    find /etc/caddy -type f -name '*leovee*' -delete 2>/dev/null || true
    systemctl reload caddy 2>/dev/null || true
  fi

  log "Deleting Leovee files"
  rm -rf /opt/leovee /var/www/leovee /var/www/"${LEOVEE_DOMAIN}" /srv/leovee
  rm -rf /etc/letsencrypt/live/"${LEOVEE_DOMAIN}" /etc/letsencrypt/renewal/"${LEOVEE_DOMAIN}".conf 2>/dev/null || true
  log "Leovee site removed from this host"
}

install_babyclaw() {
  if [[ "${SKIP_BABYCLAW_INSTALL}" == "yes" ]]; then
    log "Skipping BabyClaw install"
    return
  fi
  log "Installing BabyClaw system packages and user"
  curl -fsSL https://raw.githubusercontent.com/yogesharc/babyclaw/main/setup-vps.sh | bash
  log "Installing BabyClaw application as user babyclaw"
  su - babyclaw -c 'curl -fsSL https://raw.githubusercontent.com/yogesharc/babyclaw/main/install.sh | bash'
}

install_api() {
  if [[ ! -d "${API_SRC}" ]]; then
    echo "API sources not found at ${API_SRC}" >&2
    exit 1
  fi
  if ! id babyclaw >/dev/null 2>&1; then
    echo "User babyclaw is missing. Run the official installer first." >&2
    exit 1
  fi

  log "Installing Node API into ${API_DST}"
  mkdir -p "${API_DST}"
  cp -a "${API_SRC}/." "${API_DST}/"
  cp -a "${SCRIPT_DIR}/restart-agent.sh" "${API_DST}/restart-agent.sh"
  chown -R babyclaw:babyclaw "${API_DST}"
  chmod 700 "${API_DST}"
  chmod 700 "${API_DST}/restart-agent.sh"

  if [[ ! -f "${API_DST}/.env" ]]; then
    umask 077
    cat > "${API_DST}/.env" <<EOF
PORT=3000
NODE_ENV=production
API_TOKEN=${API_TOKEN}
ENV_FILE=/home/babyclaw/.env
ALLOWED_IPS=${ALLOWED_IPS}
TMUX_SESSION=main
START_SCRIPT=/home/babyclaw/start.sh
BABYCLAW_USER=babyclaw
RESTART_SCRIPT=${API_DST}/restart-agent.sh
EOF
    chown babyclaw:babyclaw "${API_DST}/.env"
    chmod 600 "${API_DST}/.env"
  fi

  if [[ ! -f /home/babyclaw/.env ]]; then
    install -o babyclaw -g babyclaw -m 600 /dev/null /home/babyclaw/.env
    cat > /home/babyclaw/.env <<'EOF'
TELEGRAM_TOKEN=
TELEGRAM_USER_ID=
CLAUDE_CODE_OAUTH_TOKEN=
OPENAI_API_KEY=
TELEGRAM_CHAT_ID=
WORKSPACE=/home/babyclaw/workspace
EOF
    chown babyclaw:babyclaw /home/babyclaw/.env
    chmod 600 /home/babyclaw/.env
  fi

  su - babyclaw -c "cd ${API_DST} && npm install --omit=dev"

  if ! command -v pm2 >/dev/null 2>&1; then
    npm install -g pm2
  fi

  log "Starting env API with PM2 on port 3000"
  su - babyclaw -c "cd ${API_DST} && pm2 delete babyclaw-env-api >/dev/null 2>&1 || true"
  su - babyclaw -c "cd ${API_DST} && PORT=3000 pm2 start ecosystem.config.cjs"
  su - babyclaw -c "pm2 save"
  env PATH="$(dirname "$(command -v node)"):$PATH" pm2 startup systemd -u babyclaw --hp /home/babyclaw >/dev/null || true

  if [[ -d /etc/nginx/sites-available ]]; then
    cp "${API_SRC}/nginx-babyclaw-api.conf" /etc/nginx/sites-available/babyclaw-api.conf
    ln -sfn /etc/nginx/sites-available/babyclaw-api.conf /etc/nginx/sites-enabled/babyclaw-api.conf
    nginx -t && systemctl reload nginx || true
  fi

  if command -v ufw >/dev/null 2>&1; then
    ufw allow 3000/tcp comment 'babyclaw-env-api' || true
  fi
}

start_agent_tmux() {
  if ! id babyclaw >/dev/null 2>&1; then
    return
  fi
  if [[ ! -f /home/babyclaw/start.sh ]]; then
    log "BabyClaw start.sh not present yet; skip tmux start"
    return
  fi
  log "Ensuring tmux session 'main' exists"
  su - babyclaw -c "tmux has-session -t main 2>/dev/null || tmux new-session -d -s main 'bash /home/babyclaw/start.sh'" || true
}

print_summary() {
  local ip
  ip="$(curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
  cat <<EOF

=== BabyClaw + env API ready ===
API:      http://${ip}:3000/health
Auth:     Authorization: Bearer ${API_TOKEN}
Env file: /home/babyclaw/.env
Tmux:     su - babyclaw then  tmux attach -t main

Store the API token in the Flutter app. It will not be shown again
unless you read /home/babyclaw/env-api/.env
EOF
}

remove_leovee
install_babyclaw
install_api
start_agent_tmux
print_summary

#!/usr/bin/env bash
# Shared-host edge: public :443 → SNI router; Leovee TLS terminates in Caddy (127.0.0.1:18443).
# Other vhosts keep nginx TLS on 127.0.0.1:4443 (patched from former 0.0.0.0:443).
set -euo pipefail

LEOVEE_DOMAIN="${LEOVEE_DOMAIN:-staging.leovee.lork.cloud}"
CADDY_HTTP_PORT="${CADDY_HTTP_PORT:-18080}"
CADDY_HTTPS_PORT="${CADDY_HTTPS_PORT:-18443}"
NGINX_TLS_PORT="${NGINX_TLS_PORT:-4443}"
NGINX_CONF="/etc/nginx/nginx.conf"
HTTP_SITE="/etc/nginx/sites-available/leovee-caddy-http.conf"
STREAM_SNIP="/etc/nginx/snippets/leovee-caddy-stream.conf"
SITES_DIR="/etc/nginx/sites-enabled"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the VPS." >&2
  exit 1
fi

echo "[edge] patching nginx site listen 443 → 127.0.0.1:${NGINX_TLS_PORT} (backup *.bak-leovee-edge)"
for site in "${SITES_DIR}"/*; do
  [[ -f "${site}" ]] || continue
  [[ "${site}" == *.bak-* ]] && continue
  if grep -qE 'listen .*443' "${site}"; then
    cp -a "${site}" "${site}.bak-leovee-edge"
    sed -i -E \
      -e "s/^[[:space:]]*listen[[:space:]]+443 ssl(.*);/    listen 127.0.0.1:${NGINX_TLS_PORT} ssl\\1;/" \
      -e "s/^[[:space:]]*listen[[:space:]]+\\[::\\]:443 ssl(.*);/    # leovee-edge: ipv6 tls handled by stream :443/" \
      "${site}"
  fi
done

cat >"${HTTP_SITE}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${LEOVEE_DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:${CADDY_HTTP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

mkdir -p /etc/nginx/snippets
cat >"${STREAM_SNIP}" <<EOF
map \$ssl_preread_server_name \$leovee_tls_backend {
    ${LEOVEE_DOMAIN} 127.0.0.1:${CADDY_HTTPS_PORT};
    default          127.0.0.1:${NGINX_TLS_PORT};
}
EOF

if ! grep -q 'leovee-caddy-stream' "${NGINX_CONF}"; then
  cp -a "${NGINX_CONF}" "${NGINX_CONF}.bak-leovee-edge"
  cat >>"${NGINX_CONF}" <<'NGINX_EOF'

# Leovee: SNI passthrough (scripts/setup_vps_edge_nginx.sh)
stream {
    include /etc/nginx/snippets/leovee-caddy-stream.conf;
    server {
        listen 443;
        listen [::]:443;
        proxy_pass $leovee_tls_backend;
        ssl_preread on;
    }
}
NGINX_EOF
fi

ln -sf "${HTTP_SITE}" "/etc/nginx/sites-enabled/leovee-caddy-http.conf"
nginx -t
systemctl reload nginx
echo "[edge] OK: ${LEOVEE_DOMAIN} HTTP→Caddy:${CADDY_HTTP_PORT}, HTTPS SNI→Caddy:${CADDY_HTTPS_PORT} (other hosts→nginx:${NGINX_TLS_PORT})"

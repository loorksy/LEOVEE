#!/usr/bin/env bash
# Production deploy on the VPS. Run ON the server, from the repo checkout, with
# /opt/leovee/.env already written by scripts/generate_prod_env.sh.
#
# Differs from deploy_staging_vps.sh in three ways that matter:
#   * overlay is docker-compose.prod.yml (ENVIRONMENT=production from .env, which
#     arms validate_production_startup), never docker-compose.staging.yml;
#   * Caddy owns :80/:443 on the host and issues its own certificate;
#   * the leovee_app password is re-applied after migrations, because migration
#     007 assigns the literal 'leovee_app' every time it runs.
#
# Never prints a secret value.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

# Which side terminates TLS.
#   caddy    — dedicated host: the caddy service takes :80/:443 and does its own ACME.
#   external — a reverse proxy already on this host (nginx, another Caddy) holds the
#              certificate and proxies to 127.0.0.1:3000 (web) and :8000 (api).
#              Nothing in the compose stack binds a public port in this mode.
LEOVEE_EDGE="${LEOVEE_EDGE:-caddy}"
case "${LEOVEE_EDGE}" in
  caddy | external) ;;
  *) echo "ERROR: LEOVEE_EDGE must be 'caddy' or 'external' (got '${LEOVEE_EDGE}')" >&2 && exit 1 ;;
esac

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)
[[ "${LEOVEE_EDGE}" == "caddy" ]] && COMPOSE_FILES+=(--profile edge)

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

dump_and_fail() {
  local svc="$1" why="$2"
  echo "ERROR: ${svc} — ${why}" >&2
  echo "========== last 120 lines: ${svc} =========="
  compose logs --no-color --tail 120 "${svc}" >&2 || true
  exit 1
}

# ---------------------------------------------------------------- preflight ---
command -v docker >/dev/null 2>&1 || fail "docker is not installed on this host."
docker compose version >/dev/null 2>&1 || fail "the docker compose plugin is not available (need 'docker compose', not 'docker-compose')."

# In caddy mode the stack needs the host's :80 and :443 for ACME. On a host
# already serving other sites the bind fails partway through `up`, after
# migrations have already run — and the fix is not to force it. Check before
# touching anything rather than half-deploying and then discovering it.
if [[ "${LEOVEE_EDGE}" == "caddy" ]] && command -v ss >/dev/null 2>&1; then
  occupied="$(ss -tlnH '( sport = :80 or sport = :443 )' 2>/dev/null |
    awk '{print $4}' | grep -vE '^(127\.|\[::1\])' || true)"
  if [[ -n "${occupied}" ]]; then
    fail "something already listens on :80/:443 —
$(ss -tlnpH '( sport = :80 or sport = :443 )' 2>/dev/null | sed 's/^/       /')
       Caddy needs both ports for its ACME challenge.
       Do NOT free them by stopping the incumbent — that takes down whatever it
       serves. Either deploy to a dedicated host, or keep that proxy as the edge
       and re-run with LEOVEE_EDGE=external, having pointed it at
       127.0.0.1:3000 (web) and 127.0.0.1:8000 (api). docs/VPS_DEPLOY.md covers both."
  fi
fi

[[ -f .env ]] || fail ".env missing. Generate it first: scripts/generate_prod_env.sh \"${ROOT}/.env\""

grep -qE '^ENVIRONMENT=production$' .env ||
  fail "ENVIRONMENT must be 'production' in .env — refusing. (generate_prod_env.sh sets it; generate_staging_env.sh does not.)"
grep -qE '^OANDA_ENVIRONMENT=practice$' .env ||
  fail "OANDA_ENVIRONMENT must be 'practice' in .env — refusing deploy."
if grep -qiE '^OANDA_EXECUTION=(1|true|yes|on|enabled)$' .env; then
  fail "OANDA_EXECUTION is enabled in .env — order execution is out of scope (ADR 0005). Refusing deploy."
fi
grep -qE '^TRUST_PROXY_HEADERS=true$' .env ||
  fail "TRUST_PROXY_HEADERS must be true — the API runs behind Caddy and the boot guard refuses otherwise."

# Read the values the deploy itself needs. `set -a` would export the whole file
# into this shell; pull out only these two so nothing else leaks into subprocesses.
env_value() {
  # Last assignment wins, matching how docker compose reads the file.
  sed -n "s/^$1=//p" .env | tail -n 1
}
LEOVEE_APP_DB_PASSWORD="$(env_value LEOVEE_APP_DB_PASSWORD)"
LEOVEE_DOMAIN="$(env_value LEOVEE_DOMAIN)"

[[ -n "${LEOVEE_APP_DB_PASSWORD}" ]] ||
  fail "LEOVEE_APP_DB_PASSWORD missing from .env — regenerate with the current scripts/generate_prod_env.sh."
[[ -n "${LEOVEE_DOMAIN}" ]] || fail "LEOVEE_DOMAIN missing from .env — Caddy cannot request a certificate without it."

echo "[deploy] production stack for ${LEOVEE_DOMAIN}"

# ---------------------------------------------------------------- database ----
echo "[deploy] starting postgres…"
compose up -d postgres
for _ in $(seq 1 60); do
  compose exec -T postgres pg_isready -U leovee -d leovee >/dev/null 2>&1 && break
  sleep 2
done
compose exec -T postgres pg_isready -U leovee -d leovee >/dev/null 2>&1 ||
  dump_and_fail postgres "pg_isready never succeeded"

echo "[deploy] running migrations (alembic upgrade head, migration role)…"
if ! compose run --rm --build migrate; then
  echo "ERROR: alembic upgrade head failed." >&2
  echo "  If the password looks wrong: POSTGRES_PASSWORD is applied by initdb on the FIRST" >&2
  echo "  boot of an empty volume only. On a volume that predates the current .env the owner" >&2
  echo "  password is still the old one, and rotating .env does not change it. Fix with:" >&2
  echo "    docker compose ${COMPOSE_FILES[*]} exec postgres psql -U leovee -d leovee \\" >&2
  echo "      -c \"ALTER ROLE leovee WITH PASSWORD '<the value now in DATABASE_MIGRATION_URL>'\"" >&2
  dump_and_fail migrate "alembic upgrade head failed"
fi

# Migration 007 does `ALTER ROLE leovee_app WITH LOGIN PASSWORD 'leovee_app'`
# unconditionally, so every upgrade resets the runtime credential to a literal
# that is published in this repository. Re-apply the real one before anything
# connects with it.
#
# The value goes in through the environment and is read back with \getenv (psql
# 14+; the image is pg16) rather than being passed as an argument: argv is world
# readable in `ps` for as long as the command runs. :'pw' then quotes it safely,
# so a password containing quotes cannot terminate the literal.
echo "[deploy] re-applying the leovee_app password (migration 007 resets it)…"
set_app_password() {
  compose exec -T -e APP_PW="${LEOVEE_APP_DB_PASSWORD}" postgres \
    psql -U leovee -d leovee -v ON_ERROR_STOP=1 --quiet <<'SQL'
\getenv pw APP_PW
ALTER ROLE leovee_app WITH LOGIN PASSWORD :'pw';
SQL
}
set_app_password >/dev/null || dump_and_fail postgres "could not set the leovee_app password"

# RLS is the tenancy boundary. The app re-checks this at boot; checking here too
# means a privileged runtime role fails the deploy rather than serving traffic.
echo "[deploy] verifying leovee_app is neither superuser nor BYPASSRLS…"
role_flags="$(compose exec -T postgres psql -U leovee -d leovee -tAX \
  -c "select rolsuper::text || ',' || rolbypassrls::text from pg_roles where rolname = 'leovee_app'")"
role_flags="${role_flags//[$'\r\n ']/}"
[[ "${role_flags}" == "false,false" ]] ||
  fail "leovee_app has superuser/BYPASSRLS (rolsuper,rolbypassrls = ${role_flags:-missing}) — it would bypass RLS. Refusing."

# ---------------------------------------------------------------- services ----
SERVICES=(redis api worker web leovee-mcp)
[[ "${LEOVEE_EDGE}" == "caddy" ]] && SERVICES+=(caddy)

echo "[deploy] building and starting ${SERVICES[*]}…"
compose up -d --build "${SERVICES[@]}"

echo "[deploy] waiting for /health/ready…"
ready=0
for _ in $(seq 1 90); do
  # 200 only. /health/ready returns 503 when a dependency is degraded, and a
  # degraded instance must not be treated as a successful deploy.
  code="$(compose exec -T api python -c "
import urllib.request, urllib.error
try:
    print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print(0)
" 2>/dev/null | tr -d '\r\n ')"
  if [[ "${code}" == "200" ]]; then
    ready=1
    break
  fi
  sleep 2
done
[[ "${ready}" -eq 1 ]] || dump_and_fail api "/health/ready never returned 200 (last code: ${code:-none})"

echo "[deploy] verifying worker…"
compose ps worker | grep -qiE 'running|up' || dump_and_fail worker "container not running"
compose exec -T worker python - <<'PY' >/dev/null || dump_and_fail worker "stream consumer not registered"
from app.workers.settings import WorkerSettings, oanda_stream_consumer_job

assert callable(oanda_stream_consumer_job)
assert oanda_stream_consumer_job in WorkerSettings.functions
PY

# ---------------------------------------------------------------- exposure ----
# docker publishes straight into the DOCKER iptables chain, bypassing UFW's INPUT
# rules — so "ufw deny 5432" proves nothing. Ask docker what it actually bound.
echo "[deploy] verifying postgres/redis are not published to the host…"
for svc in postgres redis; do
  bound="$(compose ps --format '{{.Publishers}}' "${svc}" 2>/dev/null || true)"
  if grep -qE '0\.0\.0\.0|\[::\]' <<<"${bound}"; then
    fail "${svc} is published on a public interface (${bound}). docker-compose.prod.yml should reset its ports."
  fi
done

echo
echo "[deploy] production stack is up — https://${LEOVEE_DOMAIN}"
echo "[deploy] commit: $(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo
echo "Next, once only:"
echo "  1. Create the first admin (choose a strong password; it is not stored in .env):"
echo "       docker compose ${COMPOSE_FILES[*]} exec -e OWNER_EMAIL=<you@example.com> \\"
echo "         -e OWNER_PASSWORD='<strong>' api python -m app.cli.ensure_owner_admin"
echo "  2. Sign in, then Settings → Secrets: enter OANDA_API_TOKEN/ACCOUNT_ID (practice"
echo "     only) and ANTHROPIC/OPENAI keys. They apply immediately, no redeploy."
echo "  3. Back up ENCRYPTION_KEY from .env somewhere durable. Rotating or losing it"
echo "     makes every secret entered in step 2 undecryptable."

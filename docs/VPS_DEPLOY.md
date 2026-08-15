# VPS deploy

Two topologies. **Production** is below; staging is unchanged at the bottom.

---

# Production

Dedicated VPS, Caddy owns `:80`/`:443` and issues its own certificate.
Overlay is `docker-compose.yml` + `docker-compose.prod.yml` — never `staging`.

Read `docs/PRODUCTION_READINESS.md` first.

## What lives where

The stack splits secrets into two layers, and putting one in the other's place is
the usual way a deploy goes wrong.

**Bootstrap only — must be in `.env` before the process starts:**
`SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`, `DATABASE_MIGRATION_URL`,
`REDIS_URL`, `ENVIRONMENT=production`, `TRUST_PROXY_HEADERS`, `LEOVEE_DOMAIN`,
`ACME_EMAIL`, `POSTGRES_PASSWORD`, `LEOVEE_APP_DB_PASSWORD`.

**Runtime, entered in the admin panel — keep these OUT of `.env`:**
`OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`OPENROUTER_API_KEY`. They are stored encrypted in the database and applied
without a redeploy (`app/services/platform_secrets.py`). The boot guard does not
require them: a missing provider degrades analysis to `NO_TRADE` with a named
reason, it does not stop the API from serving.

## 1. Generate `.env` on the server

Two distinct database passwords. `generate_prod_env.sh` refuses the built-in
`leovee` / `leovee_app` literals and refuses to let the two roles share one.

```bash
cd /opt/leovee
PG_PW="$(openssl rand -hex 24)"
APP_PW="$(openssl rand -hex 24)"
SECRET_KEY="$(openssl rand -hex 32)" \
ENCRYPTION_KEY="$(openssl rand -hex 32)" \
LEOVEE_DOMAIN=app.example.com \
ACME_EMAIL=you@example.com \
DATABASE_URL="postgresql+asyncpg://leovee_app:${APP_PW}@postgres:5432/leovee" \
DATABASE_MIGRATION_URL="postgresql+asyncpg://leovee:${PG_PW}@postgres:5432/leovee" \
  bash scripts/generate_prod_env.sh /opt/leovee/.env
```

**Back up `ENCRYPTION_KEY` before going further.** It is the parent key for every
secret an admin later enters in the panel. Rotate or lose it and those rows
cannot be decrypted — there is no recovery path, only re-entry.

Point the domain's `A` record at the VPS *before* the next step: Caddy's ACME
challenge has to reach it, and repeated failures hit Let's Encrypt rate limits.

## 2. Deploy

```bash
bash scripts/deploy_prod_vps.sh
```

It runs migrations under the migration role, re-applies the `leovee_app`
password (migration `007` resets it to a literal on every upgrade), starts the
stack, and then refuses to report success unless:

- `/health/ready` returns **200**, not 503;
- `leovee_app` is neither `SUPERUSER` nor `BYPASSRLS`;
- Postgres and Redis are not published on a public interface.

That last one is checked by asking docker what it bound, not by reading firewall
rules: docker publishes into the `DOCKER` iptables chain and bypasses UFW's
`INPUT` rules entirely, so `ufw deny 5432` proves nothing.

## 3. First admin

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec \
  -e OWNER_EMAIL=you@example.com -e OWNER_PASSWORD='<strong>' \
  api python -m app.cli.ensure_owner_admin
```

Idempotent — re-running it resets that user's password and re-asserts
`SUPER_ADMIN`.

## 4. Provider secrets, from the panel

Sign in → **Settings → Secrets** → enter `OANDA_API_TOKEN` and
`OANDA_ACCOUNT_ID` (**practice only**) and an `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY`. Applied immediately, encrypted at rest, no redeploy.

## 5. Verify

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://app.example.com/health/ready
```

Then sign in and run an XAUUSD analysis. A direction *or* a `NO_TRADE` with a
named reason both count as success; an unhandled error does not.

## Rolling back

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
git checkout <previous-sha> && bash scripts/deploy_prod_vps.sh
```

Do **not** add `-v`: that deletes the `pgdata` and `redisdata` volumes.

## Known gotchas

- `POSTGRES_PASSWORD` is applied by `initdb` on the **first** boot of an empty
  volume only. Rotating it in `.env` afterwards does not change the running
  database — you have to `ALTER ROLE leovee` by hand. The deploy script says so
  when migrations fail on authentication.
- The chart is in a documented degraded state until the TradingView runtime is
  vendored (`frontend/vendor/tradingview/README.md`). `loadLibrary.ts` reports
  the missing asset rather than rendering an empty rectangle.
- If this VPS already serves other sites on `:80`/`:443`, do not use this
  topology. Use `docker/caddy/Caddyfile` (loopback + PROXY protocol) behind
  `scripts/setup_vps_edge_nginx.sh` instead of `Caddyfile.prod`.

---

# Staging

## Option A — GitHub Actions (recommended)

**Use `docs/DEPLOY_FROM_GITHUB.md`** (phone-friendly). Workflow: **Actions → Deploy staging**.

Required secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SECRET_KEY`.

The workflow writes `/opt/leovee/.env` from secrets, deploys, health-checks, then runs live Playwright.

## Option B — From your laptop

```bash
export VPS_HOST=72.60.83.140
export VPS_USER=root
export VPS_SSH_KEY_PATH=~/.ssh/your_vps_key
git clone https://github.com/loorksy/LEOVEE.git && cd LEOVEE
./scripts/remote_deploy_vps.sh
```

Note `remote_deploy_vps.sh` pins `ENVIRONMENT=staging` and the staging overlay.
It is not a production path.

## On-server `.env`

- `OANDA_ENVIRONMENT=practice` only
- `DATABASE_URL` → `leovee_app` (see `.env.example`)
- Do not expose Postgres/Redis publicly (bind `127.0.0.1` via `docker-compose.staging.yml`)

## Tear-down

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml down -v
```

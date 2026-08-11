# VPS staging deploy (without Cursor secrets)

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

## On-server `.env`

- `OANDA_ENVIRONMENT=practice` only
- `DATABASE_URL` → `leovee_app` (see `.env.example`)
- Do not expose Postgres/Redis publicly (bind `127.0.0.1` via `docker-compose.staging.yml`)

## Tear-down

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml down -v
```

# VPS staging deploy (without Cursor secrets)

## Option A — GitHub Actions (recommended)

Add repository secrets:

| Secret | Example |
|--------|---------|
| `VPS_HOST` | `72.60.83.140` |
| `VPS_SSH_PRIVATE_KEY` | PEM for `root` (or deploy user) |
| `VPS_USER` | optional, default `root` |

Then: **Actions → Deploy staging (VPS) → Run workflow** (branch `main`).

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

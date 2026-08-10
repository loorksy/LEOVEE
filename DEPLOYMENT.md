# Leovee — Deployment & Operations

**Scope:** Local development, Docker production layout, CI/CD, secrets, TLS, migrations, backups, health checks, observability hooks.  
**Stack reference:** `ARCHITECTURE.md`.

---

## 1. Service topology

| Service | Image | Ports (internal) | Role |
|---------|-------|------------------|------|
| `leovee-api` | `leovee-backend` | 8000 | FastAPI HTTP + WebSocket |
| `leovee-worker` | `leovee-backend` | — | Arq workers (all queues) |
| `leovee-stream` | `leovee-backend` | — | OANDA stream supervisor (optional dedicated) |
| `leovee-mcp` | `leovee-backend` | 8090 | MCP SSE/HTTP (optional) |
| `leovee-web` | `leovee-frontend` | 80 | Static SPA + nginx |
| `postgres` | `pgvector/pgvector:pg16` | 5432 | Primary database |
| `redis` | `redis:7-alpine` | 6379 | Cache, Arq, streams, pub/sub |
| `caddy` | `caddy:2` | 443, 80 | TLS reverse proxy |

**Note:** `leovee-stream` may be merged into `leovee-worker` for small deployments; separate process recommended at scale for connection isolation.

---

## 2. Repository layout (deployment assets)

```
/
  docker/
    api.Dockerfile
    worker.Dockerfile
    web.Dockerfile
    caddy/Caddyfile
  docker-compose.yml              # Local full stack
  docker-compose.prod.yml         # Single-server production
  .env.example
  backend/
  frontend/
  scripts/
    migrate.sh
    backup_pg.sh
    restore_pg.sh
```

---

## 3. Dockerfiles

### 3.1 Backend (`docker/api.Dockerfile`)

- Base: `python:3.12-slim`
- Install build deps for asyncpg; non-root user `leovee`
- `pip install` from `backend/pyproject.toml` (Poetry or uv — documented in implementation)
- `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`
- **Health:** `GET /health/live` (process up), `GET /health/ready` (DB + Redis)

### 3.2 Worker (`docker/worker.Dockerfile`)

- Same image as API; different CMD:
- `CMD ["arq", "app.workers.settings.WorkerSettings"]`

### 3.3 Frontend (`docker/web.Dockerfile`)

- Stage 1: `node:20-alpine` — `npm ci`, `npm run build`
- Stage 2: `nginx:alpine` — copy `dist/`, custom `nginx.conf` for SPA fallback
- Inject `VITE_API_URL` at build time

---

## 4. docker-compose (local)

`docker-compose.yml` services:

- `postgres` with volume `pgdata`, env `POSTGRES_DB=leovee`
- `redis` with AOF persistence optional for dev
- `api` depends on postgres + redis; mounts source for hot reload in dev override file `docker-compose.dev.yml`
- `worker` same image
- `web` depends on `api`
- `caddy` optional for local HTTPS

**Dev override:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`

---

## 5. Production compose (`docker-compose.prod.yml`)

- No source mounts
- Resource limits (CPU/memory) per service
- `restart: unless-stopped`
- Secrets via environment files **not** committed — Docker secrets or host env injection
- Single-node default; horizontal scale: multiple `api` + `worker` behind load balancer sharing Redis/Postgres

---

## 6. Reverse proxy & TLS

**Default: Caddy** (`docker/caddy/Caddyfile`):

```
leovee.example.com {
  reverse_proxy web:80
  handle /api/* {
    reverse_proxy api:8000
  }
  handle /api/v1/ws {
    reverse_proxy api:8000
  }
}
```

TLS automatic via Let's Encrypt. For Nginx + certbot, alternate config documented in comment block.

**Security headers** (Caddy or nginx):

- `Strict-Transport-Security`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY` (except MCP app iframe origins)
- `Content-Security-Policy` for SPA

---

## 7. Environment variables (`.env.example`)

Grouped reference — values are placeholders; never commit real secrets.

### 7.1 Core

| Variable | Description |
|----------|-------------|
| `ENVIRONMENT` | development \| staging \| production |
| `SECRET_KEY` | JWT signing |
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `CORS_ORIGINS` | Comma-separated |
| `PUBLIC_URL` | https://leovee.example.com |

### 7.2 Encryption

| Variable | Description |
|----------|-------------|
| `ENCRYPTION_KEY` | Local dev master key (Fernet) |
| `KMS_PROVIDER` | local \| aws \| gcp |
| `AWS_KMS_KEY_ID` | Production |

### 7.3 LLM

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | |
| `OPENAI_API_KEY` | |

### 7.4 Market data

| Variable | Description |
|----------|-------------|
| `OANDA_API_TOKEN` | Platform practice account for shared data |
| `OANDA_ENVIRONMENT` | practice \| live |

### 7.5 News / email / payments

| Variable | Description |
|----------|-------------|
| `FINNHUB_API_KEY` | |
| `RESEND_API_KEY` | |
| `EMAIL_FROM` | notifications@leovee.example.com |
| `STRIPE_SECRET_KEY` | |
| `STRIPE_WEBHOOK_SECRET` | |

### 7.6 Observability

| Variable | Description |
|----------|-------------|
| `SENTRY_DSN` | Optional |
| `LOG_LEVEL` | INFO |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional |

### 7.7 Arq / workers

| Variable | Description |
|----------|-------------|
| `ARQ_MAX_JOBS` | 10 |
| `ARQ_QUEUE_NAMES` | market,agent,learning,... |

---

## 8. Database migrations

### 8.1 Strategy

1. Build new API image with Alembic revisions.
2. Run **one-shot migration job** before rolling new API:

```bash
./scripts/migrate.sh
# docker compose run --rm api alembic upgrade head
```

3. Roll API + workers.
4. Rollback: deploy previous image; run `alembic downgrade -1` only if revision reversible (test in staging).

### 8.2 Extensions

First migration:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 8.3 RLS

Apply policies in dedicated migrations; use superuser role only for migrations, app role `leovee_app` without BYPASSRLS.

---

## 9. Backup & restore

### 9.1 PostgreSQL

`scripts/backup_pg.sh`:

- `pg_dump -Fc` daily to object storage (S3-compatible)
- Retain 30 daily, 12 monthly
- Include pgvector data in same dump

### 9.2 Restore

`scripts/restore_pg.sh` — restore to new instance, verify `vector` extension, run smoke tests.

### 9.3 Redis

- AOF enabled in production for durability of rate-limit state (acceptable to rebuild cache).
- Not primary data store — no critical-only-in-Redis design.

---

## 10. Health checks

| Endpoint | Purpose | K8s probe |
|----------|---------|-----------|
| `GET /health/live` | Process alive | liveness |
| `GET /health/ready` | DB + Redis ping | readiness |
| `GET /health/startup` | Migrations complete | startup |

Worker health: Redis heartbeat key `worker:{hostname}:ping` refreshed every 30s.

Stream supervisor: `stream:oanda:status` key with last tick timestamp.

---

## 11. Graceful shutdown

**API:**

- On SIGTERM: stop accepting WS; drain connections 30s max
- Uvicorn graceful shutdown timeout 30s

**Workers:**

- Arq `on_shutdown`: finish in-flight jobs or requeue
- Stream consumer: checkpoint offset, disconnect OANDA cleanly

**Deploy order:** workers (stop stream) → migrate → API → workers (start) → web.

---

## 12. CI pipeline (GitHub Actions)

File: `.github/workflows/ci.yml`

**Jobs:**

1. **backend-lint** — `ruff check`, `ruff format --check`
2. **backend-types** — `mypy app`
3. **backend-test** — `pytest` with postgres + redis service containers
4. **frontend-lint** — `eslint`
5. **frontend-types** — `tsc --noEmit`
6. **frontend-test** — `vitest` (when present)
7. **frontend-build** — `npm run build`
8. **docker-build** — build images on main/tags (publish optional)

**Branch protection:** require CI pass before merge.

**Deploy workflow** (manual or tag-triggered):

- Build & push images to registry
- SSH or orchestrator pull + `docker compose up -d`
- Run migrations
- Smoke: `/health/ready`, login test user

---

## 13. Logging & error tracking

- **structlog** JSON to stdout in production
- Fields: `request_id`, `user_id`, `workspace_id`, `agent_run_id`
- **Sentry** SDK behind abstraction — capture unhandled exceptions, scrub PII

Log aggregation: ship stdout to Loki/CloudWatch/Datadog (operator choice — not bundled).

---

## 14. Metrics

Expose Prometheus metrics at `GET /metrics` (auth in production via network policy or admin token):

- `http_request_duration_seconds`
- `llm_tokens_total`
- `oanda_stream_connected`
- `arq_queue_size`
- `websocket_connections_active`
- `memory_retrieval_duration_seconds`

---

## 15. Scaling guidelines

| Component | Scale trigger |
|-----------|---------------|
| API | CPU > 60%, p95 latency |
| Worker | Queue depth sustained |
| Stream | Symbol count / OANDA conn limits |
| Postgres | Storage, connection pool — read replicas for analytics later |
| Redis | Memory — separate instance for cache vs Arq optional |

WebSocket sticky sessions or shared pub/sub required for multi-API fan-out (Redis pub/sub implemented in API layer).

---

## 16. Local development (without Docker)

Prerequisites: Python 3.12, Node 20, local PostgreSQL with pgvector, Redis.

```bash
cd backend && uv sync && alembic upgrade head && uvicorn app.main:app --reload
cd frontend && npm ci && npm run dev
arq app.workers.settings.WorkerSettings
```

Use `.env` from `.env.example`.

---

## 16.1 VPS test environment (optional)

Use a **disposable VPS** only for manual integration checks; **CI and default developer tests do not require a VPS**.

| Rule | Configuration |
|------|----------------|
| 1. Broker credentials | **OANDA practice (demo) only.** Set `OANDA_ENVIRONMENT=practice` and `OANDA_API_TOKEN` from env on the VPS. Never store live `api-fxtrade.oanda.com` tokens or hosts. |
| 2. Secrets | Load from VPS env / secret manager only. Do not commit `.env`. Do not log tokens (even truncated). Run `scripts/check_no_committed_secrets.sh` before push. |
| 3. Database | Isolated Postgres instance; `DATABASE_MIGRATION_URL` for `alembic upgrade head`; `DATABASE_URL` as `leovee_app`. Never point at production or shared DBs. |
| 4. Guarantees | No SQLite fallback, no synthetic providers in app code, no BYPASSRLS/superuser for the app role, no RLS weakening for tests. |
| 5. LLM | Tests use stubs in `backend/app/tests/doubles/`. No live model sweeps; optional single smoke test only with documented cost. |
| 6. Tear-down | `docker compose down -v` (or drop test DB) after runs. Document commands below. |
| 7. Firewall | Expose **443/80** (API) only if needed; **do not** expose Postgres (5432) or Redis (6379) publicly. |

**Services (docker-compose on VPS):** `postgres`, `redis`, `api`, `worker` — same as §4.

**Run backend tests on VPS:**

```bash
export TEST_DATABASE_MIGRATION_URL="postgresql+asyncpg://postgres:<pw>@127.0.0.1:5432/leovee_vps_test"
export TEST_DATABASE_URL="postgresql+asyncpg://leovee_app:leovee_app@127.0.0.1:5432/leovee_vps_test"
cd backend && pip install -e ".[dev]" && alembic upgrade head && pytest
```

**Tear-down:**

```bash
docker compose down -v
# or: dropdb leovee_vps_test
```

**Before any test touching OANDA practice API:** confirm rules 1–7 on the VPS (practice token only, isolated DB, firewall, no secrets in repo).

---

## 17. Launch readiness checklist (Phase 43)

- [ ] All health endpoints green
- [ ] Migrations applied on staging matching prod
- [ ] Backup restore drill completed
- [ ] Stripe webhooks verified in staging
- [ ] OANDA stream reconnect + gap backfill tested
- [ ] Tenant isolation test suite green
- [ ] Rate limits verified
- [ ] CSP and TLS A rating
- [ ] Runbook for incident + OANDA outage
- [ ] Sentry receiving test events

---

## 18. MCP deployment

- Optional service `leovee-mcp` exposing SSE on internal port 8090
- Not exposed publicly by default — VPN or authenticated gateway
- Same `DATABASE_URL` and secrets as API (read-only DB role optional for strict mode)

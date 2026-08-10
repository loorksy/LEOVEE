# Leovee — incident & operations runbook (Phase 43)

## Severity levels

| Level | Examples | Response |
|-------|----------|----------|
| S1 | Data breach, cross-tenant leak | Page on-call, freeze deploys, rotate secrets |
| S2 | API down, migrations failed | Roll back image, restore DB if needed |
| S3 | OANDA stream stale, elevated 5xx | Failover to REST backfill, scale workers |

## API unavailable

1. Check `GET /health/live` and `/health/ready` on the load balancer target.
2. Inspect API logs for DB/Redis connection errors.
3. Confirm Postgres and Redis are reachable from the API network (not public).
4. Roll back to previous image if failure started after deploy.
5. If migrations failed mid-deploy, run `scripts/migrate.sh` with `DATABASE_MIGRATION_URL` after fixing schema.

## OANDA outage or stream disconnect

1. Verify `OANDA_ENVIRONMENT=practice` on staging; never use live tokens on test VPS.
2. Check worker logs for `oanda_stream_consumer_job` / stream consumer errors.
3. Rely on scheduled `candle_backfill_job` to repair gaps via REST.
4. WebSocket clients should reconnect; confirm `stream disconnect → backfill` integration tests pass in CI.
5. If OANDA is globally down, pause stream jobs and surface `SYSTEM_ALERT` (notifications phase) — manual comms to users.

## Database

- **Backup:** `scripts/backup_pg.sh` (schedule daily). Dry-run: `scripts/backup_pg.sh --dry-run`.
- **Restore drill:** restore to isolated instance with `scripts/restore_pg.sh`, run `scripts/smoke_staging.sh` and `pytest` against test DB.
- Never point staging VPS at production databases.

## Security incidents

1. Run `scripts/check_no_committed_secrets.sh`.
2. Rotate `SECRET_KEY`, API keys, OANDA token, Stripe keys as applicable.
3. Re-run tenant isolation suite (`test_rls_isolation.py`, `test_multi_tenant_security_s100.py`).

## Contacts & escalation

Document on-call rotation and vendor status pages (OANDA, Stripe, cloud provider) in your team wiki — not stored in git.

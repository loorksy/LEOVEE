# §114 checklist — PR phases 42–43 (deployment + launch readiness)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] `scripts/migrate.sh`, `backup_pg.sh`, `restore_pg.sh`, `smoke_staging.sh`, `deploy_staging_vps.sh` (+ compose helpers)
- [x] `docker-compose.prod.yml`, `docker-compose.staging.yml`, `docker/caddy/Caddyfile`
- [x] `test_deployment_phases_42_43.py` — script dry-runs + health/smoke contract
- [x] Compose stack contract — `test_compose_stack_contract.py` (leovee-mcp + metrics edge)
- [x] Alembic up/down on clean DB — `test_alembic_up_down.py`
- [x] Password reset + rate-limit coverage — `test_password_reset_and_metrics_auth.py`
- [x] `docs/RUNBOOK.md`, `docs/LAUNCH_READINESS.md` (§17)
- [x] CI: deployment script dry-run step — `secrets-scan` job runs migrate/backup dry-run
- [ ] Owner LAUNCH_READINESS sign-off — **reason:** see `docs/BLOCKED_ON_OWNER.md`
- [ ] Re-run backup/restore with production-like row counts on VPS — **reason:** owner action after deploy; scripts already print candle/memory/embedding counts (`scripts/restore_pg_compose.sh`)

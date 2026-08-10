# §114 checklist — PR phases 42–43 (deployment + launch readiness)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] `scripts/migrate.sh`, `backup_pg.sh`, `restore_pg.sh`, `smoke_staging.sh`, `deploy_staging_vps.sh` (+ compose helpers)
- [x] `docker-compose.prod.yml`, `docker-compose.staging.yml`, `docker/caddy/Caddyfile`
- [x] `test_deployment_phases_42_43.py` — script dry-runs + health/smoke contract
- [x] `docs/RUNBOOK.md`, `docs/LAUNCH_READINESS.md` (§17)
- [x] CI: deployment script dry-run step — `secrets-scan` job runs migrate/backup dry-run
- [ ] Owner LAUNCH_READINESS sign-off — **reason:** see `docs/BLOCKED_ON_OWNER.md`
- [ ] Re-run backup/restore with production-like row counts on VPS after Batch 7 — **reason:** scheduled closeout

# §114 checklist — PR phases 42–43 (deployment + launch readiness)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] `scripts/migrate.sh`, `backup_pg.sh`, `restore_pg.sh`, `smoke_staging.sh`, `deploy_staging_vps.sh`
- [ ] `docker-compose.prod.yml`, `docker-compose.staging.yml`, `docker/caddy/Caddyfile`
- [ ] `test_deployment_phases_42_43.py` — script dry-runs + health/smoke contract
- [ ] `docs/RUNBOOK.md`, `docs/LAUNCH_READINESS.md` (§17)
- [ ] CI: deployment script dry-run step

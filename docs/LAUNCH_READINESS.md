# Launch readiness — DEPLOYMENT.md §17 (Phase 43)

Use this checklist before production launch. Staging VPS (§16.1) should satisfy the deploy-related items.

| Item | Owner | Staging | Production |
|------|-------|---------|------------|
| Health endpoints green (`/health/live`, `/ready`, `/startup`) | Eng | ☐ | ☐ |
| Migrations applied (`scripts/migrate.sh` / compose `migrate` job) | Eng | ☐ | ☐ |
| Backup restore drill (`backup_pg.sh` + `restore_pg.sh`) | Eng | ☐ | ☐ |
| Stripe webhooks verified (`test_stripe` / dashboard) | Eng | ☐ | ☐ |
| OANDA stream reconnect + gap backfill | Eng | ☐ | ☐ |
| Tenant isolation suite green (§100) | Eng | ☐ | ☐ |
| Rate limits verified (auth + entitlements) | Eng | ☐ | ☐ |
| CSP / TLS (Caddy or CDN) | Eng | ☐ | ☐ |
| Runbook reviewed (`docs/RUNBOOK.md`) | Eng | ☐ | ☐ |
| Sentry test event (`capture_message` / DSN) | Eng | ☐ | ☐ |

**Sign-off**

- Engineering lead: __________________ Date: __________
- Product / launch: __________________ Date: __________

**Notes**

- Staging deploy: `scripts/deploy_staging_vps.sh` (requires `.env`, practice OANDA only).
- Tear-down: `docker compose -f docker-compose.yml -f docker-compose.staging.yml down -v`

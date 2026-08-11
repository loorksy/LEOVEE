# §114 checklist — PR phases 39–40 (observability, security)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `015_api_keys` + RLS
- [x] Request ID middleware (`X-Request-ID`) + structlog fields
- [x] Sentry bridge (`SENTRY_DSN`) + worker `request_id` propagation — DSN itself is owner-blocked; unit verify in `test_sentry_bridge.py`
- [x] `/metrics` exposes `http_requests_total` / duration sums
- [x] Security headers middleware (CSP, X-Frame-Options, …) — API middleware + SPA CSP on Caddy `handle` block
- [x] API keys CRUD + scope checks — `integration/test_api_keys_phase_40.py`
- [x] §100 `test_multi_tenant_security_s100.py`
- [x] Frontend dev CSP headers in `vite.config.ts`
- [x] Restrict `/metrics` at edge (private CIDRs in Caddyfile) + API bearer in staging/production (`METRICS_BEARER_TOKEN`, `test_password_reset_and_metrics_auth.py`)
- [ ] Sentry verification with real DSN in Sentry UI — **reason:** owner must supply DSN (`docs/BLOCKED_ON_OWNER.md`)

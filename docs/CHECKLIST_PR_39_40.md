# §114 checklist — PR phases 39–40 (observability, security)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `015_api_keys` + RLS
- [x] Request ID middleware (`X-Request-ID`) + structlog fields
- [x] Sentry bridge (`SENTRY_DSN`) + worker `request_id` propagation — DSN itself is owner-blocked
- [x] `/metrics` exposes `http_requests_total` / duration sums
- [x] Security headers middleware (CSP, X-Frame-Options, …)
- [x] API keys CRUD + scope checks — `integration/test_api_keys_phase_40.py`
- [x] §100 `test_multi_tenant_security_s100.py`
- [x] Frontend dev CSP headers in `vite.config.ts`
- [ ] Restrict `/metrics` at edge (internal or basic auth) — **reason:** currently public in Caddyfile; Batch 7
- [ ] Sentry verification with real DSN — **reason:** owner must supply DSN

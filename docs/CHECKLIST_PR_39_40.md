# §114 checklist — PR phases 39–40 (observability, security)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] Migration `015_api_keys` + RLS
- [ ] Request ID middleware (`X-Request-ID`) + structlog fields
- [ ] Sentry bridge (`SENTRY_DSN`) + worker `request_id` propagation
- [ ] `/metrics` exposes `http_requests_total` / duration sums
- [ ] Security headers middleware (CSP, X-Frame-Options, …)
- [ ] API keys CRUD + scope checks
- [ ] §100 `test_multi_tenant_security_s100.py` (conversations, api keys, …)
- [ ] Frontend dev CSP headers in `vite.config.ts`

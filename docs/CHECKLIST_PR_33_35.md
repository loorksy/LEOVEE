# §114 checklist — PR phases 33–35 (performance, MCP, MCP Apps)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `013_mcp_sessions` (mcp_sessions, mcp_audit_events + RLS)
- [x] §99 `test_performance_aggregates.py` — summary matches DB aggregates
- [x] §99 integration `test_mcp_phases_33_35.py` — workspace escape, audit/usage, CSP manifest
- [x] `GET /api/v1/performance/summary` with calibration bins
- [x] `GET /metrics` Prometheus stub — present (edge auth pending Batch 7)
- [x] MCP HTTP bridge `POST /api/v1/mcp/tools/invoke`; `leovee-mcp --list-tools`
- [x] ext-apps manifests: chart + recommendation (`contentSecurityPolicy`, bearer auth) — `ext-apps/*.json` (+ packaged under `backend/app/mcp/apps/`)
- [x] Frontend `PerformanceDashboard` routed — `frontend/src/features/performance/PerformancePage.tsx` at `/performance`, summary from `/api/v1/performance/summary`; smoke tests in `PerformancePage.test.tsx` (Batch 4)
- [x] Separate `leovee-mcp` compose service — `docker/mcp.Dockerfile`, `leovee-mcp` in `docker-compose.yml` / staging; Caddy `/api/v1/mcp/*` → sidecar; `test_mcp_service.py`


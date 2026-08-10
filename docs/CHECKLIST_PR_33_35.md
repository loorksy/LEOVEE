# §114 checklist — PR phases 33–35 (performance, MCP, MCP Apps)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `013_mcp_sessions` (mcp_sessions, mcp_audit_events + RLS)
- [x] §99 `test_performance_aggregates.py` — summary matches DB aggregates
- [x] §99 integration `test_mcp_phases_33_35.py` — workspace escape, audit/usage, CSP manifest
- [x] `GET /api/v1/performance/summary` with calibration bins
- [x] `GET /metrics` Prometheus stub — present (edge auth pending Batch 7)
- [x] MCP HTTP bridge `POST /api/v1/mcp/tools/invoke`; `leovee-mcp --list-tools`
- [x] ext-apps manifests: chart + recommendation (`contentSecurityPolicy`, bearer auth) — `backend/app/mcp/apps/*.json`
- [ ] Frontend `PerformanceDashboard` routed — **reason:** Batch 3/4
- [ ] Separate `leovee-mcp` compose service — **reason:** Batch 5

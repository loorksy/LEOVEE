# §114 checklist — PR phases 33–35 (performance, MCP, MCP Apps)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] Migration `013_mcp_sessions` (mcp_sessions, mcp_audit_events + RLS)
- [ ] §99 `test_performance_aggregates.py` — summary matches DB aggregates
- [ ] §99 integration `test_mcp_phases_33_35.py` — workspace escape, audit/usage, CSP manifest
- [ ] `GET /api/v1/performance/summary` with calibration bins
- [ ] `GET /metrics` Prometheus stub
- [ ] MCP HTTP bridge `POST /api/v1/mcp/tools/invoke`; `leovee-mcp --list-tools`
- [ ] ext-apps manifests: chart + recommendation (`contentSecurityPolicy`, bearer auth)
- [ ] Frontend `PerformanceDashboard` calibration chart

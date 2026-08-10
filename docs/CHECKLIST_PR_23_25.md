# §114 checklist — PR phases 23–25 (chart semantic + KLineChart)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] §99 unit: `test_chart_semantic.py` — `backend/app/tests/test_chart_semantic.py`
- [x] §99 integration: `test_chart_semantic.py` — `backend/app/tests/integration/test_chart_semantic.py`
- [x] §99 frontend: vitest `chartAdapter.test.ts`, `ChartAnnotationRenderer.test.ts` — `frontend/src/chart/`
- [x] `chart_annotations` RLS — `test_rls_isolation.py` / chart RLS cases
- [x] Chart API: `/api/v1/chart/annotations`, `/semantic/validate`, `/semantic/persist` — `backend/app/api/routes/chart.py`
- [x] WebSocket `channels=annotations` + `workspace_id` incremental events — `backend/app/api/websocket.py`, realtime broadcaster
- [x] KLineChart 9.8.12 only in `frontend/src/chart/` — `package.json` + adapter
- [ ] Chart/annotation UI routed in `App.tsx` — **reason:** components exist; Batch 3 wires routes

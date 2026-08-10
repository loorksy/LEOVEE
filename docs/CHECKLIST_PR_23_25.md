# §114 checklist — PR phases 23–25 (chart semantic + KLineChart)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] §99 unit: `test_chart_semantic.py` (time/price geometry, lifecycle, engine build)
- [ ] §99 integration: `test_chart_semantic.py` (persist, API, adapter contract)
- [ ] §99 frontend: vitest `chartAdapter.test.ts`, `ChartAnnotationRenderer.test.ts`
- [ ] `chart_annotations` RLS; `test_rls_blocks_cross_workspace_chart_annotations`
- [ ] Chart API: `/api/v1/chart/annotations`, `/semantic/validate`, `/semantic/persist`
- [ ] WebSocket `channels=annotations` + `workspace_id` incremental annotation events
- [ ] KLineChart 9.8.12 only in `frontend/src/chart/` (`createChartEngine` / adapter)

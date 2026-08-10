# §114 checklist — PR phase 22 (thesis monitoring)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] §99 unit: `test_thesis_monitor.py` (structure break → INVALIDATED) — `backend/app/tests/test_thesis_monitor.py`
- [x] §99 integration: `test_thesis_monitor.py` + events row + recommendation sync — `backend/app/tests/integration/test_thesis_monitor.py`
- [x] `thesis_events` RLS; cross-workspace carry-over — RLS suite
- [x] Arq `thesis_monitor_job` scheduled — `backend/app/workers/settings.py`

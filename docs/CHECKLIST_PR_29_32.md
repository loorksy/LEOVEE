# §114 checklist — PR phases 29–32 (watchlists, alerts, journal, memory UI)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `012_alerts_journal` + RLS on alerts, notifications, journal_entries — alembic + RLS tests
- [x] §99 unit: `test_alert_price.py`
- [x] §99 integration: `test_ops_phases_29_32.py` — watchlist, alert trigger, journal promote, memory delete recompute
- [x] Watchlists: CRUD + `ws_symbols` + `with_quotes` — API routes
- [x] Alerts: price condition evaluation + notification fan-out + WS `notifications` — service + mock trigger path
- [x] Journal: promote → `lessons` row — `journal_service.promote_to_lesson`
- [x] Memory API: browse/patch/delete + `/calibration`; delete triggers `run_memory_recompute`
- [x] Frontend: `MemoryPanel` routed + calibration chart live — `frontend/src/features/memory/MemoryPage.tsx` at `/memory` (Batch 3)
- [x] Frontend: `WatchlistPage` routed at `/watchlist` — lists watchlists/symbols, `with_quotes=true` polling + live `/ws/v1/stream?channels=candles` quote updates; smoke tests in `WatchlistPage.test.tsx` (Batch 4)
- [x] Frontend: `AlertsPage` routed at `/alerts` — create/list alerts, mock trigger demo, notifications rendered from `/ws/v1/stream?channels=notifications`; smoke tests in `AlertsPage.test.tsx` (Batch 4)
- [x] Frontend: `JournalPage` routed at `/journal` — create/list entries + promote-to-lesson flow; smoke tests in `JournalPage.test.tsx` (Batch 4)
- [x] Market-driven alert worker — `alert_evaluation_job` + `run_alert_evaluation_cycle` (`backend/app/services/alert_evaluation.py`, `integration/test_alert_evaluation_worker.py`)

# §114 checklist — PR phases 29–32 (watchlists, alerts, journal, memory UI)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `012_alerts_journal` + RLS on alerts, notifications, journal_entries — alembic + RLS tests
- [x] §99 unit: `test_alert_price.py`
- [x] §99 integration: `test_ops_phases_29_32.py` — watchlist, alert trigger, journal promote, memory delete recompute
- [x] Watchlists: CRUD + `ws_symbols` + `with_quotes` — API routes
- [x] Alerts: price condition evaluation + notification fan-out + WS `notifications` — service + mock trigger path
- [x] Journal: promote → `lessons` row — `journal_service.promote_to_lesson`
- [x] Memory API: browse/patch/delete + `/calibration`; delete triggers `run_memory_recompute`
- [ ] Frontend: `MemoryPanel` routed + calibration chart live — **reason:** panel exists; Batch 3 enables route
- [ ] Market-driven alert worker (not only mock trigger) — **reason:** Batch 4

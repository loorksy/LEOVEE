# §114 checklist — PR phases 29–32 (watchlists, alerts, journal, memory UI)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] Migration `012_alerts_journal` + RLS on alerts, notifications, journal_entries
- [ ] §99 unit: `test_alert_price.py`
- [ ] §99 integration: `test_ops_phases_29_32.py` (watchlist, alert trigger, journal promote, memory delete recompute)
- [ ] Watchlists: CRUD + `ws_symbols` + `with_quotes`; WS candle `channel: watchlist`
- [ ] Alerts: price condition evaluation + notification fan-out + WS `notifications` channel
- [ ] Journal: promote → `lessons` row
- [ ] Memory API: browse/patch/delete + `/calibration`; delete triggers `run_memory_recompute`
- [ ] Frontend: `MemoryPanel` + calibration chart (phase 32)

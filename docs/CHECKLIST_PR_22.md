# §114 checklist — PR phase 22 (thesis monitoring)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] §99 unit: `test_thesis_monitor.py` (structure break → INVALIDATED)
- [ ] §99 integration: `test_thesis_monitor.py` + events row + recommendation sync
- [ ] `thesis_events` RLS; `test_rls_blocks_cross_workspace_research_items` (carry-over)
- [ ] Arq `thesis_monitor_job` scheduled

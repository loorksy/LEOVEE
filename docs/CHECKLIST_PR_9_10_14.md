# §114 checklist — PR phases 9, 10, 14

- [x] `cd backend && ruff check app && ruff format --check app` — CI `lint`
- [x] `cd backend && mypy app` — CI `typecheck`
- [x] `cd backend && pytest` (Postgres, `leovee_app`) — CI `test`
- [x] §99 unit: `test_market_intelligence.py`, `test_mtf_engine.py` — `backend/app/tests/`
- [x] §99 integration: `test_news_research.py`, analysis path includes MTF + intelligence — `backend/app/tests/integration/test_news_research.py`, `test_pipeline_e2e.py`
- [x] RLS on `research_items`; cross-workspace test updated — `test_rls_isolation.py`
- [x] `scripts/check_no_committed_secrets.sh` passes — CI `secrets-scan`
- [x] No production mocks; Finnhub fails closed without `FINNHUB_API_KEY` — provider + `test_blockers.py` / news tests

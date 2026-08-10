# §114 checklist — PR phases 9, 10, 14

- [ ] `cd backend && ruff check app && ruff format --check app`
- [ ] `cd backend && mypy app`
- [ ] `cd backend && pytest` (Postgres, `leovee_app`)
- [ ] §99 unit: `test_market_intelligence.py`, `test_mtf_engine.py`
- [ ] §99 integration: `test_news_research.py`, analysis path includes MTF + intelligence
- [ ] RLS on `research_items`; cross-workspace test updated
- [ ] `scripts/check_no_committed_secrets.sh` passes
- [ ] No production mocks; Finnhub fails closed without `FINNHUB_API_KEY`

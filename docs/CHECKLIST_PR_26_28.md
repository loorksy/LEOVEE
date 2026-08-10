# §114 checklist — PR phases 26–28 (chat, recommendations, trades)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] §99 unit: `test_chat_recall.py`, `test_chat_summary.py`, `test_recommendation_lifecycle.py`, `test_trade_execution_gate.py`
- [ ] §99 integration: `test_chat_recommendations.py` (RECALL + terminal recommendation)
- [ ] RLS: trades + conversations/messages cross-workspace isolation (carry-over patterns)
- [ ] Chat: RECALL bundle, summarized history, streaming SSE (`recall` + token chunks), chat actions
- [ ] Recommendations: lifecycle PATCH, `?cards=true` list, card payload
- [ ] Trades: idea CRUD; `execution_enabled` rejected with 403

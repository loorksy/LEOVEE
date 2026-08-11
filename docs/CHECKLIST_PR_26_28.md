# §114 checklist — PR phases 26–28 (chat, recommendations, trades)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] §99 unit: `test_chat_recall.py`, `test_chat_summary.py`, `test_recommendation_lifecycle.py`, `test_trade_execution_gate.py`
- [x] §99 integration: `test_chat_recommendations.py` — `backend/app/tests/integration/test_chat_recommendations.py`
- [x] RLS: trades + conversations/messages cross-workspace isolation — multi-tenant security suite
- [x] Chat: RECALL bundle, summarized history, chat actions — API routes + services
- [x] Chat provider-native streaming — **Batch 8.** `LLMProvider.stream()` from OpenAI/Anthropic → `chat_stream.iter_chat_turn_stream` → SSE (`POST .../messages?stream=true`) → `postMessageStream` + incremental `ChatPage`. Tests: `test_chat_streaming.py` (provider parity, mid-stream fallback without duplicate assistant row, client disconnect leaves no assistant, partial event order) + `ChatPage.test.tsx`
- [x] Recommendations: lifecycle PATCH, `?cards=true` list, card payload — recommendations API + `RecommendationCard.tsx`
- [x] Trades: idea CRUD; `execution_enabled` rejected with 403 — `test_trade_execution_gate.py`
- [x] Chat / recommendations / trades UI routes enabled — `ChatPage` `/chat`, `RecommendationsPage` `/recommendations`, `TradesPage` `/trades` (Batch 3 + Batch 8)

# §114 checklist — PR phases 17, 18, 20

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI jobs
- [x] §99: `test_reasoning_adversarial.py`, `test_memory_embedding.py`, E2E uses `complete_pipeline` + real reasoning — those test modules + `integration/test_pipeline_e2e.py`
- [x] Single `POST /analysis/run` with `complete_pipeline` — `backend/app/api/routes/analysis.py` (no `/analysis/pipeline`, no baseline reasoning module)
- [x] ModelRouter + `model_configs` seed; HNSW index on `memory_embeddings` — `providers/llm/router.py`, alembic migrations, seed
- [x] Memory checklist: hybrid retrieval path, embedding worker — `memory_service` / `memory/embedding.py`, `memory_embedding_index_job`
- [ ] Dedicated provider §99 (Anthropic/OpenAI generate/stream/tools/fallback) — **reason:** Batch 2 work; providers exist with thin coverage

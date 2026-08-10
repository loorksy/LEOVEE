# §114 checklist — PR phases 17, 18, 20

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] §99: `test_reasoning_adversarial.py`, `test_memory_embedding.py`, E2E uses `complete_pipeline` + real reasoning
- [ ] `reasoning_baseline` removed; `/analysis/pipeline` removed — single `POST /analysis/run` with `complete_pipeline`
- [ ] ModelRouter + `model_configs` seed; HNSW index on `memory_embeddings`
- [ ] Memory checklist: hybrid retrieval path, embedding worker

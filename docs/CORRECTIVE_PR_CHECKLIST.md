# Corrective PR — Phases 5–22 blockers (exit checklist)

## Blocker 1 — PostgreSQL + RLS
- [x] Test suite runs on PostgreSQL (`TEST_DATABASE_URL` / CI `pgvector/pgvector:pg16` service)
- [x] Alembic migrations through `006_leovee_app_role` (learning tables, RLS, partitioned candles, pgvector column)
- [x] ORM uses `JSONB` / `Vector` (no SQLite JSON shim)
- [x] `test_rls_isolation.py` — `SET ROLE leovee_app` + session vars; cross-workspace denial on tenant tables

## Blocker 2 — No production mocks
- [x] OANDA / LLM providers fail without credentials (`DataUnavailableError` / `ProviderConfigurationError`)
- [x] `validate_production_startup()` in API lifespan
- [x] Test doubles under `app/tests/doubles/` only
- [x] `test_blockers.py` — no synthetic market path without explicit fixtures

## Blocker 3 — Learning pipeline (Phase 21)
- [x] `OutcomeRecorder` + `run_learning_pipeline` (stats, symbol profiles, calibration, decay)
- [x] Terminal hooks on recommendation/thesis status transitions
- [x] Arq `process_learning_outcome` job (replaces placeholders)
- [x] Integration test: outcome → profile recall with `LOW_SAMPLE`

## Blocker 4 — OANDA streaming (Phase 7)
- [x] `OandaPricingStream` (reconnect/backoff)
- [x] `OandaStreamManager` REST fallback + gap bucket helper
- [x] Unit tests: tick aggregation / dedupe (`test_engines_unit.py`)

## Process note
Further phase work should land in **3–4 phases per PR** with tests and §114 verification. Do **not** merge `cursor/complete-remaining-phases-199e` until this corrective chain is accepted.

# Corrective PR — Phases 5–22 blockers (exit checklist)

## Blocker 1 — PostgreSQL + RLS (runtime enforced)
- [x] Tests and API use `DATABASE_URL` as **`leovee_app`** (non-superuser, no BYPASSRLS)
- [x] Alembic uses **`DATABASE_MIGRATION_URL`** (privileged) only
- [x] `get_db_session` clears GUCs; `get_workspace_context` sets `app.tenant_id` / `app.workspace_id` / `app.user_id`
- [x] Tests: `pg_roles` asserts on `leovee_app`; API list recommendations isolation; zero rows without workspace GUC

## Blocker 2 — No production mocks
- [x] OANDA / LLM fail closed; production startup validation; test doubles in `tests/doubles/`

## Blocker 3 — Learning pipeline (Phase 21)
- [x] OutcomeRecorder, pipeline, terminal hooks, Arq `process_learning_outcome`, recall integration test

## Blocker 4 — OANDA streaming (Phase 7)
- [x] `OandaCandleStreamConsumer` + Arq `oanda_stream_consumer_job` (stream → aggregate → persist → `CandleBroadcaster`)
- [x] Reconnect triggers REST `persist_backfill` via `OandaStreamManager`
- [x] WebSocket `/ws/v1/stream?symbols=EURUSD` fans out published candles (Redis optional)
- [ ] Full §99 stream disconnect → fallback → backfill HTTP mock integration (follow-up PR)

## Deferred (not on this branch)
- Post–phase-22 route modules live on branch `cursor/post-phase-22-deferred-199e` (from prior corrective snapshot).

## Process
- Phases 5–22 continue in **3–4 phases per PR** with §99 tests + §114 checklist. **Phase 23 blocked** until accepted.

# PR: Phases 7, 8, 11 + baseline E2E pipeline

**Branch:** `cursor/pr-phase-7-8-11-baseline-199e`  
**Process:** 3–4 phases per PR; §99 integration tests + §114 checklist per PR.  
**Out of scope for this PR:** Phases 9, 10, 14, 17, 18, 20, 22 (separate PRs per roadmap).

---

## Exit criteria (from `IMPLEMENTATION_PLAN.md`)

### Phase 7 — OANDA integration (REST + streaming + backfill)

**Scope (plan):** `MarketDataProvider`; OANDA REST; stream consumer with reconnect, backoff; gap backfill via REST.

**Tests (plan):** Mock OANDA; reconnect backfill idempotency.

**This PR delivers:**

- §99 integration test: stream disconnect → REST fallback → backfill on reconnect (HTTP-mocked `fetch_candles`), asserting a **gapless** M1 candle series over the recovered window.
- No change to production OANDA URLs; mocks live only under `app/tests/`.

### Phase 8 — Market data normalization + candle storage/retention

**Scope (plan):** Normalized `Candle`; partitioned table; upsert ingest; retention jobs; REST `/api/v1/markets/*`.

**Tests (plan):** Duplicate/out-of-order upsert; retention job.

**This PR delivers:**

- Retention job (`candle_retention_job`) with configurable per-timeframe retention days.
- Gap detection + repair helpers (REST backfill via injected provider in tests).
- Tests: duplicate upsert, out-of-order upsert, gap detect/repair, retention deletion.
- Markets REST unchanged unless a small gap-repair admin hook is needed (worker-only for retention).

### Phase 11 — Structure / liquidity / zones / volatility engines

**Scope (plan):** Four engines + persistence to `market_events`, structures, zones tables.

**Tests (plan):** Unit per engine; sweep vs target; zone decay.

**This PR delivers:**

- Alembic migration: `market_events`, `structures`, `price_zones` (symbol-scoped artifacts).
- `persist_engine_outputs()` after analysis orchestrator runs.
- Test: persisted rows exist and match engine output for a fixture run.

**Deferred to a later PR (not blocking this PR):** sweep vs target; zone decay golden tests (engine depth).

### Baseline E2E (§99 milestone)

**Scope:** First integration test: **market → analysis → reasoning (deterministic baseline) → recommendation → thesis**.

**Notes:**

- **Reasoning** here is `reasoning_baseline.py` (deterministic, no LLM). Full `ReasoningEngine` + adversarial gate ships in PR phases **17–18**.
- Market data in tests uses **`tests/doubles/` only**, never production code paths.

---

## Planned file list

| Action | Path |
|--------|------|
| Add | `docs/PR_PHASE_7_8_11_BASELINE.md` (this file) |
| Add | `docs/DEFERRED_BRANCH_POLICY.md` |
| Add | `docs/CHECKLIST_PR_7_8_11.md` (§114 for this PR) |
| Add | `backend/alembic/versions/008_market_engine_artifacts.py` |
| Add | `backend/app/models/market_artifacts.py` |
| Add | `backend/app/services/market/retention.py` |
| Add | `backend/app/services/market/gaps.py` |
| Add | `backend/app/services/market/engine_persistence.py` |
| Add | `backend/app/services/reasoning_baseline.py` |
| Add | `backend/app/services/analysis_pipeline.py` |
| Mod | `backend/app/models/__init__.py` |
| Mod | `backend/app/core/config.py` (retention settings) |
| Mod | `backend/app/services/market_data.py` (optional gap query helper) |
| Mod | `backend/app/workers/settings.py` (`candle_retention_job`, gap repair hook) |
| Mod | `backend/app/services/analysis_service.py` (wire persistence) |
| Mod | `backend/app/api/routes/analysis.py` (`POST /pipeline` optional) |
| Add | `backend/app/tests/integration/test_stream_disconnect_backfill.py` |
| Add | `backend/app/tests/test_candle_upsert_retention.py` |
| Add | `backend/app/tests/test_engine_persistence.py` |
| Add | `backend/app/tests/integration/test_pipeline_e2e.py` |
| Mod | `docs/CORRECTIVE_PR_CHECKLIST.md` (Phase 7 §99 item) |
| Mod | `DEPLOYMENT.md` (§ VPS test environment) |
| Add | `scripts/check_no_committed_secrets.sh` |
| Mod | `.github/workflows/ci.yml` (secrets scan job) |

---

## §114 checklist (this PR)

See `docs/CHECKLIST_PR_7_8_11.md` — run `ruff`, `mypy`, `pytest` on Postgres + `leovee_app`; tenant isolation on recommendation/thesis path; no secrets in repo.

---

## VPS / provider rules (this PR)

All automated tests use **Postgres testcontainers / CI Postgres** and **HTTP mocks / `FakeMarketDataProvider`**. No live OANDA or LLM calls in CI. VPS notes documented in `DEPLOYMENT.md`; confirm rules 1–7 on the VPS before any optional manual practice-account smoke test.

---

## Deferred branch policy

See `docs/DEFERRED_BRANCH_POLICY.md`: `cursor/post-phase-22-deferred-199e` is **read-only reference** for future phases 23+; **never merge** as a substitute for official phase PRs.

# §114 checklist — PR phases 7, 8, 11 + baseline E2E

Evidence links point at paths in this repo (or CI job names). Unchecked items have a one-line reason.

- [x] `cd backend && ruff check app && ruff format --check app` — enforced in `.github/workflows/ci.yml` (`lint` job)
- [x] `cd backend && mypy app` — enforced in CI (`typecheck` job)
- [x] `cd backend && pytest` (Postgres, `DATABASE_URL` = `leovee_app`) — CI `test` job + local suite
- [x] Tenant isolation: E2E pipeline creates recommendation/thesis only for resolved workspace — `backend/app/tests/integration/test_pipeline_e2e.py`
- [x] No production mocks; test doubles only under `app/tests/doubles/` — doubles directory + CI secrets scan
- [x] RLS unchanged; no BYPASSRLS / superuser for app tests — `backend/app/tests/test_rls_isolation.py`, `test_workspace_isolation.py`
- [x] `scripts/check_no_committed_secrets.sh` passes in CI — `secrets-scan` job (+ `scripts/check_no_secret_leaks.sh`)
- [x] PR description links `docs/PR_PHASE_7_8_11_BASELINE.md` — baseline doc present and referenced from plan

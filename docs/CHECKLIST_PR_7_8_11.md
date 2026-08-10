# §114 checklist — PR phases 7, 8, 11 + baseline E2E

- [ ] `cd backend && ruff check app && ruff format --check app`
- [ ] `cd backend && mypy app`
- [ ] `cd backend && pytest` (Postgres, `DATABASE_URL` = `leovee_app`)
- [ ] Tenant isolation: E2E pipeline creates recommendation/thesis only for resolved workspace
- [ ] No production mocks; test doubles only under `app/tests/doubles/`
- [ ] RLS unchanged; no BYPASSRLS / superuser for app tests
- [ ] `scripts/check_no_committed_secrets.sh` passes in CI
- [ ] PR description links `docs/PR_PHASE_7_8_11_BASELINE.md`

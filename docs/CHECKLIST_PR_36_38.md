# §114 checklist — PR phases 36–38 (admin, billing, entitlements)

**Scope note (Batch 8):** LEOVEE_SPEC §70 and SAAS_ARCHITECTURE §9 were amended to a reduced operator admin plane (entitlements, overview, conversations, observability). The historical 28-section list is out of scope and is **not** carried as permanent debt. Phase 36 COMPLETE is judged against the amended scope.

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `014_billing_webhooks` — idempotent `(provider, external_event_id)`
- [x] Admin RBAC: `require_support_audit` vs `require_platform_admin`; support **403** on `/admin/conversations`
- [x] Billing: `GET /billing/entitlements`, checkout (manual/stripe), Stripe webhook + `test_stripe`
- [x] Entitlements: `check_metric_limit` / `record_usage` on analysis, chat, MCP (`mcp.call`)
- [x] `EntitlementError` → HTTP 403 (global handler + MCP route)
- [x] Integration `test_admin_billing_phases_36_38.py`
- [x] Admin capability endpoint: `GET /admin/me` — never 403s, returns `{role, is_support, is_platform_admin}` so the UI can build the permission matrix without duplicating backend RBAC logic (`backend/app/api/admin_deps.py::describe_admin_access`); covered by `test_admin_me_reflects_permission_matrix_for_each_role` (USER/SUPPORT/ADMIN)
- [x] Amended §70 required surfaces shipped — entitlements + overview + conversations + observability on `AdminPage` (Batch 6); Settings page also surfaces entitlements (Batch 8); platform secrets panel (`AdminSecretsPanel` / `platform_secrets`) for SUPER_ADMIN
- [x] Frontend `AdminEntitlementsPanel` routed + UI permission matrix — **Batch 6.** `frontend/src/features/admin/AdminPage.tsx` routed at `/admin` (added to `App.tsx`, nav entry enabled in `AppShell.tsx`). Composes:
  - `AdminEntitlementsPanel` — plan/limits, visible to every workspace member (`GET /billing/entitlements`)
  - `AdminOverviewPanel`, `AdminConversationsPanel`, `AdminObservabilityPanel` — platform-admin only (`GET /admin/overview`, `/admin/conversations`, `/admin/observability/agent-runs`)
  - Audit summary footer — support tier and above (`GET /admin/audit/summary`)
  - Gating via `useAdminAccess()` (queries `/admin/me`): USER role sees only the entitlements panel plus an `admin-access-restricted` hint; SUPPORT additionally sees the audit summary plus an `admin-platform-only-hint` (overview/conversations/observability queries are not even issued — `enabled: isPlatformAdmin`); ADMIN/SUPER_ADMIN see every section. Matches backend's `require_support_audit` vs `require_platform_admin` split so the UI never surfaces an avoidable 403.
  - Smoke tests: `AdminPage.test.tsx` — asserts USER hides restricted sections and never calls their APIs, SUPPORT sees audit but not platform-admin panels/queries, ADMIN sees everything (3 cases); `AdminEntitlementsPanel.test.ts` covers `formatPlanLabel`.
- [x] Isolated hard-limit tests for analysis/LLM/MCP entitlements — **Batch 6 expansion.** `backend/app/tests/test_entitlement_hard_limits.py` calls the service layer directly (no HTTP transport):
  - `test_analysis_run_hard_limit_blocks_before_market_fetch` — `analysis_service.run_analysis` raises `EntitlementError(code="limit_exceeded")`; monkeypatched `market_data.fetch_and_store_candles` proves the OANDA-practice market fetch is never reached
  - `test_chat_send_hard_limit_blocks_before_llm_call` — `chat_service.run_chat_turn` raises before the LLM provider is invoked (`FakeLLMProvider().calls == 0`)
  - `test_mcp_call_hard_limit_blocks_before_tool_dispatch` — `mcp.runtime.invoke_tool` raises before tool dispatch/audit row insert
  - `test_analysis_run_allowed_when_under_cap` and `test_check_metric_limit_ignores_unrelated_metrics` — positive-path and cross-metric isolation controls
  - All 5 tests run against the manual/default billing adapter and Postgres test DB; no production Stripe or live OANDA credentials required

# §114 checklist — PR phases 36–38 (admin, billing, entitlements)

- [x] ruff, mypy, pytest on Postgres + `leovee_app` — CI
- [x] Migration `014_billing_webhooks` — idempotent `(provider, external_event_id)`
- [x] Admin RBAC: `require_support_audit` vs `require_platform_admin`; support **403** on `/admin/conversations`
- [x] Billing: `GET /billing/entitlements`, checkout (manual/stripe), Stripe webhook + `test_stripe`
- [x] Entitlements: `check_metric_limit` / `record_usage` on analysis, chat, MCP (`mcp.call`)
- [x] `EntitlementError` → HTTP 403 (global handler + MCP route)
- [x] Integration `test_admin_billing_phases_36_38.py`
- [ ] Frontend `AdminEntitlementsPanel` routed + UI permission matrix — **reason:** Batch 6
- [ ] Isolated hard-limit tests for analysis/LLM/MCP entitlements — **reason:** Batch 6 expansion

# §114 checklist — PR phases 36–38 (admin, billing, entitlements)

- [ ] ruff, mypy, pytest on Postgres + `leovee_app`
- [ ] Migration `014_billing_webhooks` — idempotent `(provider, external_event_id)`
- [ ] Admin RBAC: `require_support_audit` vs `require_platform_admin`; support **403** on `/admin/conversations`
- [ ] Billing: `GET /billing/entitlements`, checkout (manual/stripe), Stripe webhook + `test_stripe`
- [ ] Entitlements: `check_metric_limit` / `record_usage` on analysis, chat, MCP (`mcp.call`)
- [ ] `EntitlementError` → HTTP 403 (global handler + MCP route)
- [ ] Integration `test_admin_billing_phases_36_38.py`
- [ ] Frontend `AdminEntitlementsPanel` (plan limits display)

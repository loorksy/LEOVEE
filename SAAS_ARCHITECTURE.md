# Leovee — SaaS Architecture

**Scope:** Multi-tenancy, authentication, authorization, billing, entitlements, admin control plane, and workspace product model.  
**Companion:** `ARCHITECTURE.md`, `DATABASE_SCHEMA.md`, `SAAS_ARCHITECTURE.md` (this document).

---

## 1. Tenancy hierarchy

```
Platform (Leovee)
  └── Organization (tenant)     ← billing, subscription, org admins
        └── Workspace           ← primary data isolation boundary
              └── Users (via workspace_members + roles)
```

### 1.1 Isolation rules

| Scope | Contains |
|-------|----------|
| Organization | Subscription, invoices, org-level members, tenant feature flags |
| Workspace | Conversations, analyses, trades, memory, OANDA connections, watchlists |

- Every API request resolves **`tenant_id`** and active **`workspace_id`** from auth — never trust client body alone.
- Cross-workspace access requires explicit membership on each workspace.
- Platform operators use **separate admin roles** with audited elevated access.

### 1.2 Personal workspace provisioning

On user signup (email verified):

1. Create organization (single-user default) or join invite.
2. Create default workspace: `"{name}'s Trading Workspace"`.
3. Assign `USER` workspace role with full workspace permissions for owner.
4. Attach FREE plan subscription.

---

## 2. Authentication

### 2.1 Supported flows (production)

| Flow | Status |
|------|--------|
| Email + password | Required |
| Email verification | Required before full access |
| Password reset | Token via email (Resend) |
| Refresh tokens | Rotating, stored hashed |
| Session revocation | Per-session and global logout |
| OAuth (Google, etc.) | Architecture ready — `oauth_accounts` table |
| MFA (TOTP) | Architecture ready — `mfa_secret_enc` |

### 2.2 Password security

- Hash: **Argon2id** (preferred parameters: m=65536, t=3, p=4) via passlib-compatible layer.
- Password policy: min length 12, breach check optional (Have I Been Pwned k-anonymity API).

### 2.3 Tokens

| Token | Lifetime | Storage |
|-------|----------|---------|
| Access JWT | 15 min | Memory / Authorization header |
| Refresh | 30 days | HttpOnly Secure SameSite cookie or body for API clients |

Claims: `sub` (user_id), `tenant_id`, `session_id`, optional `workspace_id`.

### 2.4 Rate limiting (auth endpoints)

| Endpoint | Limit |
|----------|-------|
| POST /auth/login | 10/min/IP + 5/min/email |
| POST /auth/signup | 5/min/IP |
| POST /auth/password-reset | 3/min/email |

### 2.5 CSRF

Cookie-based refresh flows use **double-submit cookie** or SameSite=Strict + custom header requirement on mutating routes.

---

## 3. Authorization (RBAC)

### 3.1 Roles

| Role | Scope | Typical use |
|------|-------|-------------|
| SUPER_ADMIN | Platform | Full system |
| ADMIN | Platform / tenant | Tenant administration |
| SUPPORT | Platform | Read-heavy support tools |
| ANALYST | Workspace | Advanced analysis, no billing |
| USER | Workspace | Standard trader |

Roles bind via `workspace_members.role_id` or `organization_members` for org-level admin.

### 3.2 Permissions (granular)

Examples (full list seeded in DB):

- `workspace.read`, `workspace.write`
- `analysis.create`, `analysis.read`
- `trade.read`, `trade.create`
- `billing.read`, `billing.manage`
- `memory.read`, `memory.manage`
- `admin.users.read`, `admin.users.manage`
- `admin.system.read`, `admin.system.manage`
- `admin.ai.manage`, `admin.providers.manage`
- `admin.audit.read`

Enforcement: FastAPI dependencies `require_permission("analysis.create")` + service-layer checks.

### 3.3 Admin vs user plane

| Plane | URL prefix | Audience |
|-------|------------|----------|
| User app | `/app/*` | Traders |
| Admin | `/admin/*` | Operators |

API: `/api/v1/admin/*` requires platform/tenant admin permissions.

**Support boundary:** SUPPORT cannot read chat content or memory by default — requires break-glass permission with audit.

---

## 4. Workspace product surface

Each workspace owns (spec §6):

- Conversations & chat history
- Saved analyses, recommendations, theses, trades
- Watchlists & symbols
- Chart layouts, preferences, annotations
- Alerts & notifications
- OANDA connections (DEMO default)
- AI settings & agent memory
- Usage toward subscription limits
- Journal entries

**Settings** stored in `workspaces.settings_json` with typed Pydantic views:

- Default symbols / timeframes
- Risk defaults (risk %, max positions, min R:R)
- AI preferences (verbosity, default mode)
- Memory preferences (retention, opt-out categories)
- Chart preferences (theme, indicators, session overlays)
- Notification channels

---

## 5. Billing & entitlements

### 5.1 Plans

| Plan | Positioning |
|------|-------------|
| FREE | Limited messages, analyses, no replay |
| PRO | Higher limits, memory, MCP |
| PRO_PLUS | Premium models, advanced analysis |
| ENTERPRISE | Custom limits, SSO path, manual billing |

Limits encoded in `plans.limits_json`:

- `ai_messages_per_month`
- `analysis_runs_per_month`
- `research_requests_per_month`
- `mcp_calls_per_month`
- `watchlists_max`
- `alerts_max`
- `historical_depth` (candle retention tier)
- `replay_enabled`
- `memory_retention_days`

### 5.2 Payment providers

| Provider | Role |
|----------|------|
| `ManualInvoicePaymentProvider` | **Default** (`BILLING_PROVIDER=manual`) — offline / admin marks paid |
| `StripePaymentProvider` | Production adapter when Stripe credentials are configured — checkout, subscriptions, webhooks |

**EntitlementService** reads subscription status + plan — **never** Stripe SDK in feature code.

### 5.3 Webhooks

- Stripe: `invoice.paid`, `customer.subscription.updated`, `customer.subscription.deleted`
- Verify signatures; idempotent processing table `webhook_events`.

### 5.4 Usage metering

`UsageService` records server-side:

- LLM tokens (input/output) per workspace
- Analysis runs, research runs
- MCP calls
- Chart analysis operations
- Memory operations (embeddings)

Aggregation worker rolls up to `usage_records` per billing period.

**Hard limits:** return `402` or graceful `RATE_LIMITED` with upgrade CTA — configurable per metric (soft vs hard).

---

## 6. API keys (programmatic access)

- Format: `lvk_live_...` / `lvk_test_...`
- Stored as hash; shown once on create
- Scopes: `market.read`, `analysis.read`, `analysis.write`, `recommendation.read`, `trade.read`, `memory.read`, `mcp.read`
- Expiration + revocation + audit

Used by MCP and user automation — same workspace binding.

---

## 7. OANDA connection (workspace)

- User selects **DEMO** or **LIVE** — UI clearly labeled; default DEMO.
- Token encrypted at rest (`api_token_enc`); KMS abstraction in `infrastructure/encryption.py`.
- Masked display: last 4 chars only.
- Audit: connect, disconnect, token rotate, execution enabled.

Execution (spec §19) requires:

- Deploy/server policy gate `OANDA_EXECUTION` (not a Settings UI field; staging forces `false`)
- `trade_service` hard-rejects `execution_enabled=True` until live execution is authorized
- Workspace opt-in + kill switch (future)
- Limits: max daily loss, max risk, max position size, max open trades

---

## 8. Notifications

| Channel | Implementation |
|---------|----------------|
| In-app | `notifications` table + WebSocket |
| Email | Resend templates |
| Push | Architecture stub — device tokens table future |

Types: `RECOMMENDATION_CREATED`, `THESIS_INVALIDATED`, `TARGET_REACHED`, `PRICE_ALERT`, `NEWS_ALERT`, `LESSON_CREATED`, `STRATEGY_DECAY`, `SYSTEM_ALERT`.

User preferences in workspace settings gate channels per type.

---

## 9. Admin control plane (spec §70 — reduced)

Single-operator admin module. Scope is intentionally reduced from the
historical 28-section list; unbuilt sections are **not** open debt.

Required surfaces:
1. **Entitlements** — plan/limits/subscription (`AdminEntitlementsPanel`)
2. **Overview** — platform counts (`AdminOverviewPanel`)
3. **Conversations** — operator conversation list (`AdminConversationsPanel`)
4. **Observability** — agent-run summary (`AdminObservabilityPanel`)
5. **Platform secrets** — encrypted platform credentials (`AdminSecretsPanel` / `platform_secrets`)

Permission matrix via `/admin/me` (support vs platform-admin).

### 9.1 Admin overview metrics

Counts needed for §70 Overview (users/workspaces/conversations). Deeper
metrics (tokens, MCP, job depth, learning health) are optional depth and
out of current scope.

### 9.2 AI management

Provider secrets are editable via **Platform secrets** (`platform_secrets`).
Model routing uses `model_configs` (+ env). A full multi-section AI admin
console beyond secrets/status remains out of the reduced §70 scope.

### 9.3 Feature flags

Server-side evaluation middleware remains:

`AI_CHAT`, `ADVANCED_ANALYSIS`, `RESEARCH`, `BACKTEST`, `MCP`, `OANDA_EXECUTION`, `ADVANCED_CHARTS`, `PREMIUM_MODELS`, `MEMORY`, `LEARNING`, `CROSS_TENANT_AGGREGATE_LEARNING`.

Scoped: platform → tenant → workspace override. A dedicated Feature Flags
admin section is out of §70 required scope.

---

## 10. Audit logging

Record (spec §93):

- Auth events (login, logout, password change)
- OANDA connect/disconnect
- API key create/revoke
- Billing/subscription changes
- Admin actions
- Trade execution attempts
- Memory user edit/delete
- Permission changes

Fields: `actor_user_id`, `action`, `resource_type`, `resource_id`, `ip_address`, `metadata_json`, `created_at`.

Retention: configurable; export for compliance.

---

## 11. Security boundaries (SaaS)

| Threat | Mitigation |
|--------|------------|
| IDOR on workspace | Session-derived workspace_id + membership check |
| Tenant leakage | tenant_id on all rows + RLS |
| Privilege escalation | Role changes admin-only + audit |
| Billing bypass | EntitlementService on every costly operation |
| Secret exposure | Never return decrypt tokens to FE |

Multi-tenant security tests required (spec §100).

---

## 12. User-facing application map

Sidebar routes (spec §9):

Home, AI Analyst, Chat, Markets, Watchlist, Analysis, Trades, Recommendations, Alerts, Journal, Research, Memory, Performance, Settings, Backtesting, Replay, API/MCP, Billing.

Frontend feature folders mirror these modules under `frontend/src/features/`.

---

## 13. Email templates (Resend)

| Template | Trigger |
|----------|---------|
| verify_email | Signup |
| password_reset | Reset request |
| alert_notification | Price/thesis alert |
| billing_receipt | Invoice paid |

All links point to Leovee-branded domains with short-lived tokens.

---

## 14. Compliance-oriented notes

- Data export: user can request workspace export (JSON) — future enterprise feature hook.
- Account deletion: soft-delete user + schedule workspace purge job.
- Logs must not contain passwords, tokens, or full API keys.

---

## 15. SaaS deployment identity

- Product branding: **Leovee** everywhere (UI, emails, MCP server name).
- Package names: `@leovee/web`, `leovee-backend`, `leovee-mcp` (see `IMPLEMENTATION_PLAN.md`).

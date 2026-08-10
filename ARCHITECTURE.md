# Leovee — System Architecture

**Product:** Leovee — production-grade, multi-tenant AI Forex trading analyst SaaS  
**Status:** Greenfield design (Phase 1)  
**Last updated:** 2026-08-10

---

## 1. Executive summary

Leovee is an AI market analyst workspace, not an automated trading bot. Users operate inside isolated **workspaces** within **organizations (tenants)**. The platform ingests normalized Forex market data (primary: **OANDA v20** REST + streaming), runs deterministic market engines and LLM-assisted reasoning through a layered **agent orchestrator**, persists **memory and learning** in PostgreSQL with **pgvector**, exposes **REST + WebSocket** APIs and an **MCP server (`leovee-mcp`)**, and renders analysis on **KLineChart** via a renderer-agnostic **chart semantic model**.

Design principles:

- **Recommendation-first** — execution is opt-in with hard safety controls.
- **No hallucination** — prices, indicators, news, and statistics come from tools; the LLM interprets evidence only.
- **Tenant isolation** — every query derives `tenant_id` / `workspace_id` from the authenticated session.
- **Event-driven cost control** — expensive LLM calls are triggered by meaningful events, not every tick.
- **Chart independence** — backend and agents emit semantic chart instructions; only the frontend adapter talks to KLineChart.

---

## 2. Technology stack

| Layer | Choice | Notes |
|--------|--------|--------|
| Backend runtime | Python 3.12+ | Async-first |
| API framework | FastAPI | REST + WebSocket |
| Validation / DTOs | Pydantic v2 | Shared contract shapes |
| ORM | SQLAlchemy 2.x (async) | `asyncpg` driver |
| Migrations | Alembic | No manual prod schema changes |
| Primary DB | PostgreSQL 16+ | **pgvector** required |
| Cache / queues | Redis 7+ | Cache, rate limits, Arq, pub/sub fan-out |
| Background jobs | **Arq** | See §2.1 |
| LLM | Anthropic + OpenAI SDKs | Unified `LLMProvider` + `ModelRouter` |
| Frontend | React 18+, TypeScript strict, Vite | TanStack Query, Zustand, Tailwind |
| Routing | React Router v6 | |
| Charting | **KLineChart `9.8.12`** (pinned) | v9 API only; see §7 |
| Market data | OANDA v20 REST + pricing stream | Abstract `MarketDataProvider` |
| News / calendar | **Finnhub** adapters | See §2.2 |
| Email | **Resend** | `EmailProvider` abstraction |
| Payments | **Stripe** + **manual invoice** | Entitlements processor-agnostic |
| MCP | `leovee-mcp` on MCP + ext-apps patterns | Same authZ as API |
| Logging | structlog | JSON in production |
| Quality | pytest, mypy, ruff (backend); eslint, tsc (frontend) | |

### 2.1 Background jobs: Arq (decision)

**Chosen: Arq** over Celery.

| Criterion | Arq | Celery |
|-----------|-----|--------|
| Async / FastAPI alignment | Native asyncio workers | Traditionally sync; async support added later |
| Operational surface | Single Redis dependency (already required) | Broker + often separate result backend |
| Worker model | Lightweight coroutine jobs | Heavier process pool for CPU-bound work |

Leovee workers are predominantly I/O-bound: OANDA streams, HTTP to LLM/news APIs, DB, embeddings, notifications. CPU-heavy deterministic engines run in-process with bounded inputs; if a job becomes CPU-saturated (large backfill analytics), it can be sharded by symbol/time range across Arq tasks.

**Queues (logical):**

- `market` — stream consumers, candle sync, backfill, gap repair  
- `intelligence` — structure/liquidity batch recompute (event-triggered)  
- `agent` — analysis runs, research, adversarial passes  
- `thesis` — thesis monitor ticks (batched per workspace/symbol)  
- `learning` — outcome recording, stats, calibration, lesson distillation, decay  
- `memory` — embedding generation, aging, archival  
- `notifications` — email, in-app fan-out  
- `billing` — usage aggregation, invoice sync  
- `maintenance` — retention, cleanup  

### 2.2 External provider decisions

| Provider type | Implementation | Rationale |
|---------------|----------------|-----------|
| News | `FinnhubNewsProvider` | Forex/market news API, stable REST, clear attribution fields |
| Economic calendar | `FinnhubEconomicCalendarProvider` | Same vendor reduces secret sprawl; calendar events with currency + impact |
| Email | `ResendEmailProvider` | Transactional API, templates, deliverability |
| Payments (primary) | `StripePaymentProvider` | Subscriptions, invoices, webhooks |
| Payments (fallback) | `ManualInvoicePaymentProvider` | Admin-recorded payments; entitlements unchanged |

LLM **web search** (if enabled) is supplementary only, with stored provenance — never the primary news/calendar feed.

### 2.3 Event bus: Redis Streams

Internal domain events use **Redis Streams** with consumer groups per worker type. WebSocket fan-out uses **Redis pub/sub** (or stream fan-out workers) so multiple API instances can broadcast workspace-scoped events.

Event names align with the product spec (e.g. `NEW_CANDLE`, `THESIS_INVALIDATED`, `OUTCOME_RECORDED`). Handlers are idempotent where possible (natural keys: `workspace_id + symbol + timeframe + candle_ts`).

---

## 3. Logical architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Clients: Leovee Web (React)  │  Admin UI  │  MCP Clients / MCP Apps       │
└───────────────┬───────────────────────────────┬───────────────────────────┘
                │ REST / WS                     │ MCP (stdio/SSE)
                ▼                               ▼
┌───────────────────────────┐     ┌─────────────────────────────────────────┐
│  FastAPI API Gateway       │     │  leovee-mcp (thin tool layer)          │
│  Auth, RBAC, rate limits   │     │  → Application services only           │
│  /api/v1/*, /api/v1/ws     │     └─────────────────────────────────────────┘
└───────────────┬───────────┘
                │
    ┌───────────┼───────────┬──────────────────┬─────────────────┐
    ▼           ▼           ▼                  ▼                 ▼
 Application  Agent      Domain engines    Providers         Infrastructure
 Services     Orchestrator (deterministic)  (LLM,OANDA,…)     (DB,Redis,Arq)
    │           │           │                  │                 │
    └───────────┴───────────┴──────────────────┴─────────────────┘
                │
                ▼
        PostgreSQL (+ pgvector)          Redis (cache, streams, arq)
```

### 3.1 Backend package layout

```
backend/
  app/
    api/              # Routes, WebSocket, dependencies (tenant context)
    core/             # Config, security, logging, errors, feature flags
    domain/           # Pure domain models & engine interfaces
    agents/           # Orchestrator, specialized agents
    engines/          # Market intelligence, structure, liquidity, zones, volatility,
                      # scenario, risk, decision, chart semantic, monitoring, learning
    providers/        # llm/, market/oanda, news/, calendar/, email/, payments/
    services/         # Use-cases composing domain + persistence
    infrastructure/   # DB session, redis, arq, embeddings, encryption KMS abstraction
    mcp/              # MCP server wiring (may run as separate process)
    workers/          # Arq task definitions
    models/           # SQLAlchemy ORM
    schemas/          # Pydantic API schemas
    tests/
```

### 3.2 Frontend package layout

```
frontend/
  src/
    app/              # Root providers, theme
    routes/           # Route definitions
    components/       # Shared UI
    features/         # auth, dashboard, chat, markets, …, admin
    chart/            # ChartEngine abstraction + KLineChart 9.8.12 adapter ONLY here
    api/              # Typed API client
    hooks/
    stores/           # Zustand (UI/chart local state)
    websocket/
    types/
```

**Rule:** No `import 'klinecharts'` outside `frontend/src/chart/`.

---

## 4. Request and tenancy flow

1. Client presents access token (Bearer) or secure session cookie (browser).
2. API validates token, loads `user_id`, `tenant_id`, active `workspace_id` (or resolves default workspace).
3. **Never** accept `tenant_id` / `workspace_id` from the client for authorization — only for routing hints; server verifies membership.
4. `TenantContext` dependency injects scoped DB session filters and RLS session variables (`SET app.tenant_id`, `SET app.workspace_id`).
5. All reads/writes attach `tenant_id`; workspace-owned resources attach `workspace_id`.
6. Audit log records actor, action, resource, IP (where applicable).

---

## 5. Real-time data path

### 5.1 OANDA streaming → candles

1. **Stream supervisor** (worker) maintains bounded connections per OANDA account / practice environment, respecting OANDA connection limits.
2. Tick/pricing events update an in-memory **live candle aggregator** per `symbol + timeframe`.
3. On candle boundary: emit `CANDLE_COMPLETED`; intra-bar: `CANDLE_UPDATED` / `PRICE_UPDATED`.
4. Persist via idempotent upsert into `candles` table.
5. Publish to Redis → WebSocket hub → client `ChartDataAdapter` → `KLineChartAdapter`.

### 5.2 Disconnect handling

- Exponential backoff + jitter on stream errors.
- On reconnect: REST **gap backfill** for missed ranges; merge with idempotent upserts.
- REST polling is **fallback only** when stream unhealthy (documented degraded mode).

### 5.3 WebSocket protocol (summary)

- Endpoint: `GET /api/v1/ws` (upgrade), authenticated.
- Subscribe messages include `workspace_id`, channels (`market`, `analysis`, `thesis`, `alerts`, …), symbol filters.
- Payloads are versioned JSON envelopes: `{ "type", "workspace_id", "ts", "data" }`.

---

## 6. Agent and engine interaction (summary)

Detailed design: `AGENT_ARCHITECTURE.md`, `MEMORY_ARCHITECTURE.md`.

- **Orchestration** runs the loop: PERCEIVE → RECALL → … → LEARN.
- **Deterministic engines** produce structured evidence with provenance.
- **LLM** receives bounded context: recent chat, summaries, retrieved memory (labeled), live tool outputs.
- **Tools** are the only path to market data, memory search, risk math, and chart annotation proposals.
- **MemoryWriter** (LLM-assisted) proposes lessons; **OutcomeRecorder** is fully deterministic.

---

## 7. Chart architecture

### 7.1 KLineChart version

- **Pinned dependency:** `klinecharts@9.8.12` in `frontend/package.json`.
- Documentation and adapters target **v9 APIs** (`v9.klinecharts.com`).
- Major upgrades (e.g. to 10.x) are a dedicated project: adapter rewrite, regression tests, visual QA.

### 7.2 ChartSemanticModel (backend + API)

Semantic operations (renderer-agnostic), examples:

- `DRAW_ZONE`, `DRAW_STRUCTURE`, `DRAW_LIQUIDITY`, `DRAW_SETUP`, `DRAW_LEVEL`, `LABEL`
- Anchors: **timestamp + price** (and optional `timeframe` metadata for display).
- Lifecycle: `CREATED → ACTIVE → … → REMOVED` (see spec §52).

### 7.3 Frontend ChartEngine

| Module | Responsibility |
|--------|----------------|
| `ChartTypes.ts` | Shared TS types mirroring API semantic model |
| `ChartController.ts` | Facade used by features/chat |
| `ChartDataAdapter.ts` | Normalized `Candle` model, incremental updates |
| `KLineChartAdapter.ts` | Sole KLineChart import; implements ChartEngine |
| `ChartAnnotationRenderer.ts` | Semantic → overlay primitives |
| `ChartIndicatorManager.ts` | MA, EMA, RSI, etc. from server-calculated series |
| `ChartInteractionManager.ts` | Zoom, pan, crosshair |
| `ChartTimeframeManager.ts` | TF switch orchestration |

Performance: incremental candle updates, batched annotation diffs, throttled price ticks, no full chart destroy on tick.

---

## 8. Security architecture (summary)

- Passwords: **Argon2id** (preferred) or bcrypt via passlib-compatible layer.
- Tokens: short-lived access JWT + rotating refresh tokens; server-side session revocation table.
- CSRF: double-submit or SameSite strict cookies for cookie-based auth.
- Rate limits: Redis sliding window on auth and expensive endpoints.
- Secrets: envelope encryption for OANDA tokens, API keys, provider secrets (KMS abstraction: local key in dev, cloud KMS in prod).
- **RLS** on sensitive tenant tables (memory, conversations, credentials) — see `DATABASE_SCHEMA.md`.
- CSP and security headers on frontend static host.

Full SaaS authZ/billing: `SAAS_ARCHITECTURE.md`.

---

## 9. Observability

- **Correlation IDs:** `X-Request-ID` propagated to workers and agent runs (`agent_run_id`).
- **Metrics (Prometheus-compatible):** API latency histograms, LLM tokens/cost, OANDA error counters, stream uptime, WS connections, Arq queue depth, memory retrieval latency, learning pipeline lag.
- **Tracing:** OpenTelemetry hooks around HTTP, DB, Redis, LLM calls (optional exporter).
- **Error tracking:** Sentry-compatible abstraction (DSN via env).
- **Agent observability:** `agent_runs`, `agent_traces` (no chain-of-thought storage).

---

## 10. Feature flags (server-enforced)

`AI_CHAT`, `ADVANCED_ANALYSIS`, `RESEARCH`, `BACKTEST`, `MCP`, `OANDA_EXECUTION`, `ADVANCED_CHARTS`, `PREMIUM_MODELS`, `MEMORY`, `LEARNING`, `CROSS_TENANT_AGGREGATE_LEARNING` (default **off**).

Stored in `feature_flags` / plan entitlements; evaluated in middleware and services.

---

## 11. Trading sessions and time

- All DB timestamps **UTC** (`timestamptz`).
- Session detection: **IANA zones** — `Australia/Sydney`, `Asia/Tokyo`, `Europe/London`, `America/New_York`.
- Boundaries configurable per deployment; unit tests include DST transition dates.

---

## 12. Failure modes (architecture-level)

| Failure | Behavior |
|---------|----------|
| OANDA down | `DATA_UNAVAILABLE`; no synthetic candles |
| Stream down | REST fallback + backfill; degraded banner |
| News down | Lower confidence; no fabricated headlines |
| LLM primary down | ModelRouter fallback provider |
| Memory down | Degraded RECALL; analysis continues, labeled |
| Chart render error | Recommendation/analysis persisted; UI recovery path |

---

## 13. Related documents

| Document | Scope |
|----------|--------|
| `DATABASE_SCHEMA.md` | Tables, indexes, RLS, retention |
| `AGENT_ARCHITECTURE.md` | Layers, loop, tools, state machines |
| `MEMORY_ARCHITECTURE.md` | Memory types, learning, retrieval, guardrails |
| `MCP_ARCHITECTURE.md` | leovee-mcp, tools, apps, security |
| `SAAS_ARCHITECTURE.md` | Tenancy, RBAC, billing, admin |
| `DEPLOYMENT.md` | Docker, CI, TLS, backups |
| `IMPLEMENTATION_PLAN.md` | Phased delivery 1–43 |

---

## 14. Architecture decision record (ADR) index

| ID | Decision |
|----|----------|
| ADR-001 | Arq for background jobs |
| ADR-002 | Redis Streams for internal events |
| ADR-003 | KLineChart 9.8.12 pinned |
| ADR-004 | Finnhub for news + economic calendar |
| ADR-005 | Resend for email |
| ADR-006 | Stripe + manual invoice for payments |
| ADR-007 | Chart semantic model decoupled from KLineChart |
| ADR-008 | Logical multi-tenancy with RLS on sensitive data |

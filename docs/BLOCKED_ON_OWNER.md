# Blocked on owner

Items that need the product owner. Agents continue around these and do not wait.

| Item | Why needed | Status |
|------|------------|--------|
| **OANDA token rotation** | Practice token was exposed in chat; treat as compromised. New token goes **only** in `/opt/leovee/.env` on the VPS. Never in reports, logs, commits, fixtures, or chat. | Owner rotating; repo has leak checks |
| **Production Stripe credentials** | Live billing; keep `BILLING_PROVIDER=manual` (default) and Stripe in test mode until supplied | Waiting |
| **Production LLM keys** (Anthropic / OpenAI) | Live model calls in staging/prod beyond fixtures | Waiting |
| **Resend production key** | Real transactional email (verify/reset) | Waiting |
| **Finnhub production key** | News ingestion cron fails closed without it | Waiting |
| **Production domain / edge** | Whether to stay on shared nginx host or move off it | Waiting |
| **LAUNCH_READINESS sign-off** | Phase 43 human sign-off lines | Waiting |
| **`METRICS_BEARER_TOKEN` on VPS** | Staging/production `/metrics` rejects unauthenticated scrapes; set a bearer token in `/opt/leovee/.env` and configure Prometheus accordingly | Waiting |
| **Sentry DSN verification** | Bridge is wired; confirm events in Sentry UI with a real DSN | Waiting |
| **Live / funded OANDA + `OANDA_EXECUTION`** | Explicitly **not** authorized. Practice OANDA only on staging until owner reviews the completed system and authorizes live. | Forbidden until written authorization |
| **VPS backup/restore re-run** | Scripts count `candles` / `agent_memories` / `memory_embeddings`; owner should re-run after next staging deploy with real data | Waiting |

## Broker policy (non-negotiable)

- Practice OANDA only, on staging only.
- Do not add a live token to any environment.
- Do not enable `OANDA_EXECUTION`.

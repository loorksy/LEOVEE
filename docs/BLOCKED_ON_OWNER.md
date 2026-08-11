# Blocked on owner

Items that need the product owner. Agents continue around these and do not wait.

## GitHub Actions secrets (add these first)

Phone-friendly steps: `docs/DEPLOY_FROM_GITHUB.md`.

### Required for Deploy staging

| Secret | What to paste |
|--------|----------------|
| `VPS_HOST` | `72.60.83.140` |
| `VPS_USER` | `root` |
| `VPS_SSH_KEY` | Deploy private key (`-----BEGIN OPENSSH PRIVATE KEY-----` …) |
| `OANDA_API_TOKEN` | **Practice** token only |
| `OANDA_ACCOUNT_ID` | Practice account id |
| `ANTHROPIC_API_KEY` | Anthropic API key (required for mid-stream chat fallback) |
| `OPENAI_API_KEY` | OpenAI API key (required for mid-stream chat fallback) |
| `SECRET_KEY` | Random app signing key |

### Optional

| Secret | What it unlocks |
|--------|-----------------|
| `FINNHUB_API_KEY` | Research / news (UI shows “not configured” until set) |
| `RESEND_API_KEY` | Transactional email |
| `METRICS_BEARER_TOKEN` | Authenticated `/metrics` |
| `SENTRY_DSN` | Sentry |
| `ENCRYPTION_KEY` | Field encryption |
| `STRIPE_SECRET_KEY` | Stripe (keep billing manual until ready) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhooks |

**Broker policy:** never put a live/funded OANDA token in secrets. Deploy refuses non-`practice` `OANDA_ENVIRONMENT` and any enabled `OANDA_EXECUTION`.

### VPS authorized_keys (one-time)

**Done via agent SSH bootstrap** (deploy pubkey on VPS). For GitHub Actions, still paste the matching **private** key into `VPS_SSH_KEY` — the Cursor `ghs_` token cannot create Actions secrets (`403 Resource not accessible by integration`).

---

## Paste when agent asks (provider credentials)

Ready for owner paste into chat (agent will write VPS `.env` + attempt GitHub secrets):

- `OANDA_API_TOKEN` (practice)
- `OANDA_ACCOUNT_ID` (practice)
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `SECRET_KEY`

Staging currently has practice OANDA + `SECRET_KEY` set; **both LLM keys are empty** (chat mid-stream fallback needs them). `OANDA_EXECUTION=false`.

---

## Other owner items

| Item | Why needed | Status |
|------|------------|--------|
| **Merge PR #18 then #19** | Batch 1–7 + Batch 8 closeout must land on `main` before deploy | **Done** |
| **Add secrets + Run Deploy staging** | Workflow writes `/opt/leovee/.env` and deploys; Playwright runs after | Actions secrets blocked for agent token; **SSH deploy + live Playwright green** |
| **OANDA token rotation** | Practice token was exposed in chat; treat as compromised. New token → GitHub secret `OANDA_API_TOKEN` only | Owner rotating; repo has leak checks |
| **Production Stripe credentials** | Live billing; keep `BILLING_PROVIDER=manual` until supplied | Waiting |
| **Resend production key** | Real transactional email (verify/reset) | Waiting |
| **Finnhub key** | Optional secret `FINNHUB_API_KEY`; Research stays explicitly “not configured” without it | Waiting |
| **Production domain / edge** | Whether to stay on shared nginx host or move off it | Waiting |
| **LAUNCH_READINESS sign-off** | Phase 43 human sign-off lines | Waiting |
| **`METRICS_BEARER_TOKEN`** | Optional secret; staging/production `/metrics` auth | Waiting |
| **Sentry DSN verification** | Bridge is wired; confirm events with a real DSN | Waiting |
| **Live / funded OANDA + `OANDA_EXECUTION`** | Explicitly **not** authorized. Practice OANDA only on staging until written authorization | Forbidden until written authorization |
| **VPS backup/restore re-run** | Scripts count `candles` / `agent_memories` / `memory_embeddings`; re-run after next staging deploy with real data | Waiting |

## Broker policy (non-negotiable)

- Practice OANDA only, on staging only.
- Do not add a live token to any environment.
- Do not enable `OANDA_EXECUTION`.

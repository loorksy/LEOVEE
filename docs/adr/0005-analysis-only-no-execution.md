# 0005 — Analysis and recommendations only

**Status:** accepted · **Supersedes:** `LEOVEE_SPEC.md` §17 (partly), §19, §57, §105

## Context

AiChart executes trades: MetaAPI and a local MT5 bridge, broker account linking,
order placement with human-in-the-loop approval, an execution kill switch,
Telegram notifications, and web push. That is a large share of its surface — 20
`api/agent/mt/*` routes, `src/lib/execution.ts` at 31 KB, `src/lib/brokers/`,
`src/lib/metaapi/`, and roughly 14 of its 68 tables.

## Decision

None of it is migrated. Leovee is an analysis and recommendation platform. No
broker connectivity, no account linking, no order placement, no Telegram, no web
push, no external notifications of any kind. Transactional email for account
verification and password reset stays.

## Consequences

- The scope of the migration is far smaller than the raw line count suggests:
  roughly 14 tables and 35 routes fall away before any porting starts.
- **The execution guard's arithmetic is not dropped.** A plan whose stop sits
  inside the live spread, or whose reward/risk collapses once costs are applied,
  is a *bad recommendation* whether or not anyone ever places it. Those checks
  move to `app/engines/plan_sanity.py`. Only the parts that touch an order go.
- `models/trade.py` and `routes/trades.py` stay, re-purposed as a **manual
  journal of fills the user reports themselves**, feeding outcome learning.
  There is no execution path, and `test_trade_execution_gate.py` is the standing
  assertion that there is not.
- `metaapi`, `mt5`, `place_order`, `send_order`, `broker_login`, `telegram`,
  `webpush` and their packages are in the forbidden-term guard, checked on every
  run. The exclusion is mechanical rather than remembered — the migration ports
  from a codebase where all of this exists and is deeply wired in.

# 0008 — Scalp only, and the agent chooses the timeframe

**Status:** accepted · **Supersedes:** `LEOVEE_SPEC.md` §21, §49, §106

## Context

The specification treats timeframe as a user-facing control: a timeframe manager
in the chart, a selector in the analysis form, `H1` as the default. AiChart's
constitution takes the opposite view — *the trading style follows the analysed
timeframe; it is never a user-selectable mode* — and the decision doctrine
already adopted from it (ADR 0002) depends on that.

The owner has now fixed the style: **scalp only**, with the agent choosing which
frame between 1m and 15m carries the setup.

## Decision

**Decision timeframes are M1, M5 and M15.** A recommendation may only be made on
one of them. Anything slower is a different trade — different holding period,
different invalidation, different risk — not a slower view of the same one.

**The agent chooses, not the user.** There is no timeframe selector. Which frame
carries the setup depends on where structure is legible and where the move is
actually forming, which is an analytical judgement. Exposing it as a control
invites a request for a one-minute answer on a chart that has nothing to say at
one minute, and the agent would have to either comply or argue.

**Higher frames stay as context.** H4 and H1 are fetched, stored and read for
bias — never as the frame a scalp executes on. The same constitution requires an
answer to name which frame leads the decision, which gives context, and which
times the entry, so the context has to exist for that sentence to be true.

## Consequences

- `app/core/timeframes.py` is the single policy: `DECISION_TIMEFRAMES`,
  `CONTEXT_TIMEFRAMES`, and an `ACTIVE_TIMEFRAMES` union that drives fetching,
  backfill and retention.
- **M30 and D1 are dropped entirely.** M30 sits between M15 and H1 and tells a
  scalper nothing either neighbour does not; D1 is too coarse to time a
  one-minute entry and its longer-horizon bias is already carried by H4.
- The multi-timeframe stack changes from `D1/H4/H1` to `H4/H1/M15`. The stock
  stack was a swing trader's ladder; for a scalp, M15 is part of the context
  rather than an afterthought below it.
- `POST /api/v1/analysis/run` takes `timeframe` as **optional**, and rejects a
  non-scalping frame with 422 rather than quietly analysing it. The chart may
  still pin the frame it is displaying; asking for H4 is refused with the reason.
- The timeframe selector is removed from the analysis page. The result reports
  which frame the agent chose, which is the honest direction for that
  information to flow.
- `INTERIM_DECISION_TIMEFRAME` stands in until M6 ports the real selection
  logic. It is named as a stand-in rather than dressed up as a choice, on the
  same principle as the engine ledger: a placeholder that looks like a decision
  is worse than one that admits what it is.

## Open question deferred to M6

Selection itself — how the agent picks between M1, M5 and M15 — is agent logic
and lands with the specialist fleet. The candidate signals are volatility
regime, where the nearest structure sits relative to current price, and spread
as a fraction of the expected move. Until then the interim constant holds the
pipeline together and nothing reads it as evidence.

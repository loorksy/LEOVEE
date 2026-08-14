# 0002 — A successful analysis always carries a direction

**Status:** accepted · **Supersedes:** `LEOVEE_SPEC.md` §110 step 17

## Context

AiChart's agent constitution states that every successful analysis ends in one
direction — BUY or SELL — and that WAIT is never an analytical outcome or a way
to avoid deciding. When the market genuinely cannot be read, the agent names the
operational blocker instead, and never invents numbers to fill the gap.

The Leovee specification instead asks for three scenarios including an explicit
"no-trade" one, and defines `NO_TRADE` as a decision direction alongside BUY and
SELL. The two models disagree about what the product is for.

## Decision

AiChart's doctrine governs. Every result separates three layers that are never
collapsed into one another:

1. **Analytical view** — BUY or SELL. There is no third value.
2. **Plan type** — immediate, anticipatory, or conditional.
3. **Execution state** — valid now, awaiting activation, expired, invalidated,
   or blocked.

`NO_TRADE` is reserved for **operational failure** with a named cause: stale or
missing data, an engine that could not answer, an unavailable model provider.
This is the existing `fail_closed_no_trade(reason)` contract, kept as-is.

## Consequences

- `run_scenario_engine` produces two directional scenarios plus an
  **invalidation** scenario — what would falsify the thesis — rather than an
  abstention scenario.
- `NO_TRADE` must be reachable only from the fail-closed path. This is asserted
  directly rather than left as a convention.
- A direction being required does not make an entry required. When price is
  unsuitable or the move is not worth taking after costs, the direction stands
  and the plan states the price or condition that would make it executable. The
  tradability grade (`now` / `soon` / `watch_only`) carries that distinction, so
  nothing has to be dressed up as an entry to satisfy the doctrine.
- The user-facing wording for `NO_TRADE` is "analysis could not be completed:
  <cause>", not "no trade" — the difference between a blocker and a judgement.

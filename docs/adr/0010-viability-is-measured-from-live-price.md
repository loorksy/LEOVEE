# 0010 — Viability is measured from live price, never modelled from spread

**Status:** accepted · **Supersedes:** — (corrects ADR 0008's deferred question)

## Context

`plan_sanity` — the engine that asks whether a recommendation survives the market
it was written for — first landed carrying AiChart's cost model: a round-trip
charge of spread plus slippage, both paid twice, gated at three times that
figure, with a session table widening the spread in Asian hours and a static
30-pip constant standing in whenever no live quote was available.

Every one of those numbers was invented. Nobody had measured gold's spread on
this platform, and the platform has no broker, places no order, and fills
nothing — so there was no execution whose cost the model could have been
describing.

It was not harmless. At the assumed cost the first target had to clear 1.92 USD,
which needs an ATR near 2.00 USD on the one-minute frame — far above ordinary
one-minute gold. **The platform refused an entire timeframe because of a constant
nobody had measured**, and reported the refusal as a fact about the market.

That is the same defect as `zones.py` fabricating a supply zone from a single
bar at a hardcoded strength of 0.5, wearing a cost model. M0 was created to stop
engines inventing evidence; this one was inventing it about execution instead of
about structure, and the guard did not see it because the number looked like
finance.

The owner's instruction is direct: viability must not be based on spread at all,
but on the live price itself.

## Decision

**Every floor is measured from the candles. Nothing is modelled.**

- **The noise floor is the median wick** — `(high − low) − |close − open|` over
  the last 50 bars. The wick is what price gave back inside a single candle: how
  far it probed and returned, having gone nowhere. A stop inside that is swept by
  ordinary movement rather than by the thesis being wrong, and saying so requires
  no assumption about anyone's broker, because the number is in the data.
- **The target floor is `0.5 × ATR`** — measured volatility, not assumed
  friction. A target price cannot reach inside the plan's lifetime is unreachable
  whatever the execution costs.
- **An observed spread is reported and never gates anything.** When a live quote
  exists it is real information for the reader, and a wide print raises
  `SPREAD_WIDE_RIGHT_NOW`. It is a fact about this instant; a plan is not made
  unviable by it. When no quote exists, nothing is substituted — the field is
  absent rather than filled with a model.
- **Position sizing carries no cost either.** `risk.py`'s 30-pip default and its
  `spread_too_wide` rejection are removed; risk is the distance to the stop.

**The measure is the wick, not the bar range, and this distinction is the whole
decision.** The first attempt used the median *range* at a multiple of 2.0, which
is self-contradictory: median bar range *is* ATR under another name, so a stop
sized as `0.8 × ATR` can never clear `2.0 × ATR`. Measured on real bars the
headroom came out at 0.80 on M1, 0.82 on M5 and 1.18 on M15 — **no frame could
ever have passed**. The multiple is now 1.0, because the claim being made is
exactly "a stop inside the movement price routinely gives back is taken out by
that movement"; any larger multiple would be a preference dressed as a
measurement.

**Room to trade ranks a timeframe; it never excludes one.** Whether the market
leaves a stop any room is a question about a *specific plan*, and `plan_sanity`
asks it directly against that plan's own levels. Asking it during timeframe
selection, against a stop nobody has proposed yet, discarded whole frames on a
hypothetical. Only two things exclude a frame now, and both are facts about the
candles: `INSUFFICIENT_BARS` and `NO_READABLE_STRUCTURE`.

## Consequences

- Removed: `estimate_spread_pips`, `round_trip_cost_pips`, `session_at`,
  `SESSION_SPREAD_MULTIPLIER`, `GOLD_STATIC_SPREAD_PIPS`, `STATIC_SLIPPAGE_PIPS`,
  `MIN_COST_MULTIPLE`, `SpreadEstimate`, `spread_too_high`, `MAX_SPREAD_MULTIPLE`
  and the `spread_pips` parameter of `run_risk_engine`.
- Added: `PriceContext` and `measure_price_context` in `app/engines/plan_sanity.py`.
- Failure codes are now `STOP_DISTANCE_ZERO`, `NO_PRICE_CONTEXT`,
  `STOP_INSIDE_NOISE`, `NO_TARGET`, `TARGET_INSIDE_NOISE` and
  `REWARD_RISK_UNCOMPUTABLE`; warnings are `REWARD_RISK_BELOW_ONE` and
  `SPREAD_WIDE_RIGHT_NOW`.
- **A tape that cannot be measured fails rather than passes** (`NO_PRICE_CONTEXT`).
  Returning viable on a missing measurement turns "we could not tell" into a
  blanket approval, which is the class of lie this engine exists to stop telling.
- **The clock leaves the decision entirely.** The cost floor was session-shaped,
  so identical candles chose different frames depending on when the run happened
  and a replay could not reproduce it. `select_decision_timeframe` no longer takes
  a moment, reads no clock and consults no session table: the same bars always
  give the same answer, whenever they are read.
- This closes ADR 0008's deferred question, and rules out one of the three
  candidate signals it named — "spread as a fraction of the expected move" is
  precisely the modelled quantity being removed here.
- `docs/AICHART_MIGRATION_PLAN.md` records this as owner decision **D12**.

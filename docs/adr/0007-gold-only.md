# 0007 — Leovee analyses gold only

**Status:** accepted · **Supersedes:** `LEOVEE_SPEC.md` §17, §60, and the "Forex" framing throughout

## Context

The specification describes a multi-instrument Forex platform, and AiChart
carries a twenty-instrument universe: seven majors, eleven crosses, gold, and
bitcoin. The M1 port of that universe was already underway when the owner
narrowed the product: the platform, the agent, the analysis and everything
around them are for **XAUUSD only**.

## Decision

The tradable universe is a single instrument, XAUUSD. Everything else is
rejected at the data layer rather than merely absent from the UI.

The *mechanism* stays general — an allowlist, a spec per instrument, a symbol
picker shape in the frontend — while its content is one row. That costs nothing
now and makes adding silver later a one-line change rather than an excavation.

## Consequences

Most of these run in the helpful direction, which is worth stating plainly
because a narrowed scope usually reads as pure loss:

- **Per-instrument tolerances collapse to constants.** The liquidity engine's
  equal-high comparison, spread sanity, stop buffers and zone widths all depend
  on pip size. With one instrument there is one pip size (`0.01` — gold prices
  to two decimals, not the `0.0001` of a currency pair) instead of a table that
  has to be right for every row.
- **The session model is gold's, not a general case with an exception.** Gold
  halts [17:00, 18:00) New York every weekday; treating that as a special case
  of the FX week is what produced AiChart's phantom-gap bug. Here it is simply
  the calendar.
- **Memory becomes directly comparable.** A similar-case lookup no longer has to
  ask whether a EURUSD analogue means anything for gold — every past episode is
  the same market. Case retrieval, strategy statistics and confidence
  calibration all sharpen for it, and the cold-start problem (ADR 0003) shortens
  because every outcome contributes to the same sample.
- **One candle series, one stream subscription, one warm cache.** Storage,
  backfill and retention all shrink by roughly the instrument count.
- The crypto trading class disappears entirely. Unreachable branches are a
  liability, so it is removed rather than kept "just in case"; ADR 0004's
  charting decision and this one both leave the mechanism able to grow.

Enforcement:

- `app/core/symbols.py` holds the allowlist and `require_instrument` raises
  `UnknownSymbolError` rather than substituting gold. Silently answering about
  gold when asked about EURUSD would produce a confident analysis of the wrong
  market, which is worse than an error.
- `app/services/market_data.py::get_or_create_symbol` is the single chokepoint.
  It previously created a row for *any* code on demand, deriving base and quote
  by slicing the ticker and leaving `pip_location` at a positive default — for
  gold that would have been eight orders of magnitude out.
- Migration `018_seed_gold_symbol` seeds XAUUSD with correct metadata and
  removes rows for instruments the platform no longer admits.
- `frontend/src/config/symbols.ts` mirrors the list so the UI does not offer
  what the API will refuse.

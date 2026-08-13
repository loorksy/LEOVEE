# 0006 — Engines compute in float; Decimal at the money boundary

**Status:** accepted

## Context

Leovee's `OHLCBar` carried `Decimal` prices, which is the instinctively safe
choice for money. The deterministic engines are being ported from JavaScript,
where every number is an IEEE-754 double.

## Decision

Geometry, indicators, structure, liquidity, zones and regime compute on `float`.
`Decimal` is used at the money boundary only: persisted entry, stop and target
prices, and position sizing. `app/engines/bar.py::bar_from_candle` converts once,
at the edge.

## Consequences

- `Decimal` and `float` do not produce the same answers. The differences are
  usually in the last few digits, but occasionally land on a comparison boundary
  and flip a pattern from detected to missed. Since the golden fixtures pin the
  reference implementation's actual output, a `Decimal` port would flag a
  difference on nearly every fixture — and the natural response, widening the
  tolerance, would disable exactly the check the fixtures exist to provide.
- Choosing `float` for prices is a deliberate departure from the usual rule and
  needs the boundary to be real, not nominal. Nothing inside `app/engines/`
  constructs a `Decimal`, and nothing outside it consumes engine floats as
  persisted prices without an explicit conversion.
- `app/core/numeric.py` holds the JavaScript semantics that differ from Python's
  (`Math.round` is half-up toward +∞; `%` takes the sign of the numerator;
  `Math.trunc` division; `JSON.stringify` dropping `undefined` keys). Each is
  named and tested there rather than rediscovered per ported file.

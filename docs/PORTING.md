# Porting deterministic logic from AiChart

This describes how the deterministic engines move from AiChart's TypeScript into
Leovee's Python (phases M2–M4 of `AICHART_MIGRATION_PLAN.md`). It is a procedure
rather than advice, because the failure mode it prevents is invisible.

## Why not just read the code and rewrite it

Because the errors that matter do not look like errors. A window bounded at
`i - period` instead of `i - period + 1`, a comparison that used `>=`, a sort
whose tie-break differs, a rounding mode — each produces working code and
slightly different numbers. Nothing crashes. Tests written against the port pass,
because they were written by reading the port. The drift surfaces months later as
a recommendation whose stop sits a pip inside the structure it was meant to be
outside of.

Careful review does not catch this; the arithmetic is exactly the kind nobody
reads twice. So the port is not reviewed into correctness, it is **pinned** to
the reference implementation's actual output.

## The procedure

### 1. Fix the inputs

Fixtures live in `backend/app/tests/fixtures/candles/` and never read the clock —
`app/tests/bars.py::EPOCH` is the fixed start time. Two kinds, both needed:

- **Real market windows** — OANDA candles across symbols, timeframes and regimes
  (trending, ranging, high-volatility, weekend gap, session boundaries). These
  catch what happens on data that actually occurs.
- **Synthetic shapes** — the builders in AiChart's own `__tests__` directories
  (for example the `trend()` and `candle()` helpers in `candlesticks.test.ts`)
  were written to pin edge cases: a pattern one bar from completion, a doji at a
  boundary, an invalidated head-and-shoulders. They transfer to pytest with
  almost no translation and they carry the *intent*, not just the numbers. Port
  these alongside the fixtures.

### 2. Capture the reference output

Once, from the AiChart working tree, with a throwaway `tsx` script that imports
the pure module and writes JSON:

```ts
// scratch/capture-geometry.mts — not committed to AiChart
import { detectChartGeometry } from "../src/lib/chart/geometry/detectGeometry";
import { readFileSync, writeFileSync } from "node:fs";

for (const name of process.argv.slice(2)) {
  const candles = JSON.parse(readFileSync(`fixtures/${name}.json`, "utf8"));
  const snapshot = detectChartGeometry({ candles });
  writeFileSync(`golden/geometry/${name}.json`, JSON.stringify(snapshot, null, 2));
}
```

Commit the resulting JSON to
`backend/app/tests/fixtures/golden/<engine>/<fixture>.json`.

Two rules:

- **The AiChart tree is read-only.** Nothing is committed or pushed there.
- **Leovee never depends on Node.** Not at runtime, not in CI. It depends only
  on the committed JSON, which is why capture happens once rather than on every
  test run.

### 3. Port the function

Preserve the control flow literally, including the parts that look wrong.
Improvements are a **separate commit after the golden test is green** — otherwise
a genuine fix and an accidental regression arrive together and the diff cannot
tell you which is which.

Use `app/core/numeric.py` for anything JavaScript does differently:

| Trap | JavaScript | Python | Use |
|---|---|---|---|
| Rounding halves | `Math.round(2.5) === 3`, toward +∞ | `round(2.5) == 2`, banker's | `js_round` |
| Modulo of a negative | `-7 % 3 === -1`, sign of numerator | `-7 % 3 == 2`, floors | `js_mod` |
| Integer division | `Math.trunc(-7/2) === -3` | `-7 // 2 == -4` | `js_trunc_div` |
| Absent optional field | key omitted by `JSON.stringify` | `"key": null` | `drop_none` |

And compute in `float`. The reference is JavaScript, where every number is an
IEEE-754 double; running the port on `Decimal` produces different answers in the
last digits and occasionally at a comparison boundary that flips a detection.
`Decimal` belongs at the money boundary only — persisted entry/stop/target
prices and position sizing. `app/engines/bar.py` converts once, at the edge.

### 4. Assert against the reference

```python
from app.tests.golden import assert_matches_golden, golden_names

@pytest.mark.parametrize("fixture", golden_names("geometry"))
def test_geometry_reproduces_reference(fixture: str) -> None:
    snapshot = detect_chart_geometry(load_candles(fixture))
    assert_matches_golden(snapshot, "geometry", fixture)
```

**Tolerance policy:**

- **Exact** for discrete outputs: pattern type, direction, `status`, `stage`,
  `broken`, `breakDirection`, pivot indices, and array **length and order**.
  Detector output order encodes ranking; a reorder is a real difference.
- **`1e-9` relative** for arithmetic-derived prices.
- **Anything needing looser than `1e-9` is a port bug.** Fix the port. Widening a
  tolerance converts a detectable defect into an undetectable one, and it is
  never obvious later that the number was allowed through rather than verified.

### 5. Record intentional differences

If the port deliberately differs — a bug in the reference, a decision recorded in
the plan — write it in the test with the reason:

```python
# The reference clamps confidence to 100 *after* the bonus, so a stacked
# confluence could report 104. Corrected here; see M3 notes.
assert snapshot["patterns"][0]["confidence"] <= 100
```

Never absorb a known difference by loosening the comparator. The next person
cannot tell a widened tolerance from a verified match.

## What this does not cover

Anything that calls an LLM — the final decision synthesizer, the adversarial
reviewer, the memory writer. There is no golden output for a probabilistic
result, and pinning one would test the model rather than the port. Those are
covered by reference scenarios in the style of AiChart's
`test:decision-authority` suite: a described market state and the set of
decisions that may legitimately follow (BUY / SELL / a named operational
blocker), asserted on structure and invariants rather than on text.

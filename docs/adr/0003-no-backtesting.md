# 0003 — No backtesting or statistical validation

**Status:** accepted · **Supersedes:** `LEOVEE_SPEC.md` §64

## Context

AiChart ships `research-service/`: 12,789 lines of Python (FastAPI) implementing
a deterministic bar-by-bar backtest engine, statistical validation (walk-forward,
bootstrap, Monte Carlo, sensitivity analysis), declarative JSON strategy specs
and a research swarm, running on a no-egress network with a read-only rootfs.

Being already Python, it was the cheapest thing in the whole migration to move —
a lift-and-shift rather than a port.

## Decision

It is not migrated. Backtesting and statistical validation are out of scope for
Leovee entirely, by owner decision.

Also dropped: `src/lib/research/` (the Node client), `strategies/backtestCapital`,
the backtest-derived half of `strategies/evidence`, `tradingDna/backtestEvidence`,
`tradingDna/shadowTrader`, and the `api/backtests/*` routes.

**Not** dropped: the news and fundamentals research agent (§26, §27). "Research"
names two different things in AiChart and only the statistical one goes.

## Consequences

- The only source of statistical support becomes the outcomes of real
  recommendations, through the M8 learning loop. This actually matches the
  constitution's own rule — never claim statistical backing you do not have —
  more honestly than a backtest would, since a backtest measures a strategy on
  history rather than this workspace's realised results.
- Every strategy therefore starts with **no prior**. A new workspace must not
  inherit a confident calibration derived from someone else's outcomes. The
  cold-start policy is explicit and tested: wide confidence intervals,
  `watch_only` tradability, and recommendations published as "direct analysis,
  no statistical support" until a sample accumulates.
- Chart replay survives as a **visual review** tool for inspecting a past
  analysis. It is not a validation mechanism, and
  `test_replay_temporal_s101.py` continues to guard its temporal isolation.
- `backtest`, `walk_forward` and `monte_carlo` are in the forbidden-term guard
  in `app/tests/conformance/test_no_execution_surface.py`, so this cannot drift
  back in unnoticed.

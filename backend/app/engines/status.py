"""Which analytical engines are real, and which are still placeholders.

Leovee was built greenfield against a specification, and the engine layer was
stubbed to get the pipeline wired end to end. Several stubs do not merely
under-perform — they *invent* evidence. ``run_zones_engine`` returned a demand
zone and a supply zone derived from the last bar's range with a hardcoded
``strength: 0.5``; ``run_scenario_engine`` returned confidences of 0.55 and 0.35
chosen by hand. Those numbers flowed into the decision and out to the user as a
confidence figure, indistinguishable from a measured one.

A fabricated number is worse than a missing one. A missing engine can fail
closed and say so; a fabricated engine produces a confident, plausible, wrong
recommendation and nothing anywhere reports a problem.

So until an engine is genuinely implemented (M2–M4 of the migration plan), it
declares itself unavailable and the orchestrator fails closed with the reason.
This module is the ledger. Flipping an entry to ``IMPLEMENTED`` is the last step
of porting that engine, and ``test_engine_status_ledger`` keeps the ledger
honest about what is actually wired up.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

__all__ = [
    "EngineStatus",
    "ENGINE_STATUS",
    "ENGINE_NOT_IMPLEMENTED",
    "engine_unavailable",
    "is_unavailable",
    "unavailable_engines",
]


class EngineStatus(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    PLACEHOLDER = "PLACEHOLDER"


ENGINE_NOT_IMPLEMENTED = "ENGINE_NOT_IMPLEMENTED"

# Every engine the orchestrator runs, and whether its output can be trusted.
#
# PLACEHOLDER entries return a real market answer only by accident. Each one is
# ported for real in the phase named beside it; flip it to IMPLEMENTED in the
# same commit that lands the port, and the ledger test will hold you to it.
ENGINE_STATUS: dict[str, EngineStatus] = {
    # Genuine: a correct Wilder ATR over the supplied bars.
    "volatility": EngineStatus.IMPLEMENTED,
    # Genuine arithmetic over its inputs (garbage-in still applies).
    "risk": EngineStatus.IMPLEMENTED,
    "decision": EngineStatus.IMPLEMENTED,
    # Ported in M4 over the M2 primitives: swing detection, level clustering
    # and trend inference.
    "structure": EngineStatus.IMPLEMENTED,
    # Sweep detection and equal-level clustering, with the tolerance derived
    # from gold's pip size rather than a constant.
    "liquidity": EngineStatus.IMPLEMENTED,
    # Imbalance-origin zones, scored on impulse, respect and freshness, with
    # consumed zones dropped.
    "zones": EngineStatus.IMPLEMENTED,
    # Two directional scenarios plus an invalidation scenario (ADR 0002), with
    # confidence derived from evidence agreement rather than chosen by hand.
    "scenarios": EngineStatus.IMPLEMENTED,
    # M4 — derived from the placeholder engines above.
    "market_intelligence": EngineStatus.PLACEHOLDER,
    "mtf": EngineStatus.PLACEHOLDER,
}


def engine_unavailable(engine: str) -> dict[str, Any]:
    """The output a placeholder engine returns instead of an invented answer."""
    return {"status": "unavailable", "reason": ENGINE_NOT_IMPLEMENTED, "engine": engine}


def is_unavailable(output: Any) -> bool:
    return isinstance(output, dict) and output.get("status") == "unavailable"


def unavailable_engines(engines: dict[str, Any]) -> list[str]:
    """Names of engines in a result bundle that could not produce an answer."""
    return sorted(name for name, output in engines.items() if is_unavailable(output))

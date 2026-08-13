from __future__ import annotations

from typing import Any

from app.engines.status import engine_unavailable
from app.engines.volatility import OHLCBar


def run_zones_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    """Supply/demand zones — not implemented yet (M4).

    The previous stub returned one DEMAND and one SUPPLY zone spanning twice the
    last bar's range, each with a hardcoded ``strength: 0.5``. Those are not
    weak zones, they are invented ones: no accumulation, no imbalance, no
    revisit count, no relationship to anything that happened before the final
    bar. Publishing them as evidence made the analysis look grounded when it was
    not, so the engine now reports that it cannot answer and the orchestrator
    fails closed.

    The real port (order blocks, fair-value gaps, revisit strength) lands in M4.
    """
    del bars
    return engine_unavailable("zones")

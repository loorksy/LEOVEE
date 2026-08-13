from __future__ import annotations

from typing import Any

from app.engines.status import engine_unavailable
from app.engines.volatility import OHLCBar


def run_structure_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    """Market structure — not implemented yet (M4).

    The previous stub set the bias by comparing the first close to the last and
    reported the extremes of the final five bars as swing points. That is a
    direction of travel, not market structure: no swing detection, no break of
    structure, no change of character, and no notion of which timeframe the
    swing belongs to.

    M4 ports the real engine (pivots, BOS/CHoCH) on top of the M2 primitives.
    """
    del bars
    return engine_unavailable("structure")

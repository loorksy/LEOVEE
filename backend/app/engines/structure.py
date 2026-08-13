"""Market structure — real, as of M4.

Replaces the placeholder that set bias by comparing the first close to the last.
That is a statement about two bars; structure is a statement about the sequence
of swing highs and lows between them, and a series can close higher across a
clean downtrend.

The work is in app/engines/primitives/structure.py; this is the engine-shaped
wrapper the orchestrator calls.
"""

from __future__ import annotations

from typing import Any

from app.core.timeframes import MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.primitives.structure import detect_structure_levels, level_to_dict
from app.engines.status import engine_unavailable

_BIAS_BY_SHAPE = {
    "uptrend": "BULLISH",
    "downtrend": "BEARISH",
    "range": "NEUTRAL",
    "unknown": "NEUTRAL",
}


def run_structure_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    if len(bars) < MIN_CANDLES_FOR_ANALYSIS:
        # Too few bars to confirm swings. Abstaining is the honest answer; a
        # bias derived from a handful of bars is noise wearing a label.
        return engine_unavailable("structure")

    analysis = detect_structure_levels(bars)
    return {
        "bias": _BIAS_BY_SHAPE[analysis.structure],
        "shape": analysis.structure,
        "current_price": analysis.current_price,
        "swing_high": max(analysis.swing_highs) if analysis.swing_highs else None,
        "swing_low": min(analysis.swing_lows) if analysis.swing_lows else None,
        "swing_highs": analysis.swing_highs,
        "swing_lows": analysis.swing_lows,
        "nearest_support": analysis.nearest_support,
        "nearest_resistance": analysis.nearest_resistance,
        "supports": [level_to_dict(level) for level in analysis.supports],
        "resistances": [level_to_dict(level) for level in analysis.resistances],
    }

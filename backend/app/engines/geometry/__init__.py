"""Deterministic chart geometry, ported from AiChart's src/lib/chart/geometry/.

Pure and agent-independent: it imports nothing from the agent layer, so the
decision path, the rendered PNG and the MCP numeric context all consume the same
detections — a triangle the model reasons about is the exact triangle drawn on
the chart the operator sees.
"""

from __future__ import annotations

from typing import Any

from app.core.timeframes import MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.geometry.detect import detect_chart_geometry
from app.engines.status import INSUFFICIENT_DATA, engine_unavailable

__all__ = ["detect_chart_geometry", "run_geometry_engine"]


def run_geometry_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    """The engine-shaped wrapper the orchestrator calls.

    Geometry is evidence like any other engine, so it declines the same way when
    it has nothing to work with. It has no partial answer to offer: below the
    bar floor the pivots are unconfirmed, and a trendline drawn through
    unconfirmed pivots is a line through noise that looks exactly like a line
    through structure.
    """
    if len(bars) < MIN_CANDLES_FOR_ANALYSIS:
        return engine_unavailable("geometry", INSUFFICIENT_DATA)
    return detect_chart_geometry(bars).to_dict()

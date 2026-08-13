from __future__ import annotations

from typing import Any

from app.engines.status import engine_unavailable
from app.engines.volatility import OHLCBar


def run_liquidity_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    """Liquidity — not implemented yet (M4).

    The previous stub looked only at the final bar against the running extreme,
    and compared equal highs with a fixed ``1e-5`` absolute tolerance — which is
    a fraction of a pip on EURUSD and larger than a pip on a JPY cross, so the
    same code meant different things per instrument.

    M4 ports sweep detection and equal-high/low clustering with per-instrument
    tolerances derived from pip size.
    """
    del bars
    return engine_unavailable("liquidity")

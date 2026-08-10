from __future__ import annotations

from typing import Any

from app.engines.volatility import OHLCBar


def run_zones_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    if not bars:
        return {"zones": []}
    mid = (bars[-1].high + bars[-1].low) / 2
    width = (bars[-1].high - bars[-1].low) * 2
    zones = [
        {
            "type": "DEMAND",
            "low": float(mid - width),
            "high": float(mid),
            "strength": 0.5,
        },
        {
            "type": "SUPPLY",
            "low": float(mid),
            "high": float(mid + width),
            "strength": 0.5,
        },
    ]
    return {"zones": zones}

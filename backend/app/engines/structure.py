from __future__ import annotations

from typing import Any

from app.engines.volatility import OHLCBar


def run_structure_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    if len(bars) < 3:
        return {"bias": "NEUTRAL", "swing_high": None, "swing_low": None}
    highs = [float(b.high) for b in bars]
    lows = [float(b.low) for b in bars]
    swing_high = max(highs[-5:]) if len(highs) >= 5 else max(highs)
    swing_low = min(lows[-5:]) if len(lows) >= 5 else min(lows)
    bias = "BULLISH" if bars[-1].close > bars[0].close else "BEARISH"
    return {"bias": bias, "swing_high": swing_high, "swing_low": swing_low}

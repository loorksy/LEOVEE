from __future__ import annotations

from typing import Any

from app.engines.volatility import OHLCBar


def run_liquidity_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    if len(bars) < 2:
        return {"sweeps": [], "equal_highs": False, "equal_lows": False}
    last = bars[-1]
    prev_high = max(b.high for b in bars[:-1])
    prev_low = min(b.low for b in bars[:-1])
    sweeps: list[str] = []
    if last.high > prev_high and last.close < prev_high:
        sweeps.append("BUY_SIDE")
    if last.low < prev_low and last.close > prev_low:
        sweeps.append("SELL_SIDE")
    return {
        "sweeps": sweeps,
        "equal_highs": abs(float(last.high) - float(prev_high)) < 1e-5,
        "equal_lows": abs(float(last.low) - float(prev_low)) < 1e-5,
    }

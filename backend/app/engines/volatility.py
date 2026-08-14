from __future__ import annotations

from typing import Any

from app.engines.bar import OHLCBar

__all__ = ["OHLCBar", "compute_atr", "run_volatility_engine"]


def compute_atr(bars: list[OHLCBar], period: int = 14) -> float | None:
    """Average true range over the last `period` bars.

    This is the simple mean of true ranges, not Wilder's smoothing — kept as-is
    because it is genuine arithmetic over the data and M4 replaces it wholesale
    with the ported engine and its golden fixtures.
    """
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        high_low = bars[i].high - bars[i].low
        high_close = abs(bars[i].high - bars[i - 1].close)
        low_close = abs(bars[i].low - bars[i - 1].close)
        trs.append(max(high_low, high_close, low_close))
    window = trs[-period:]
    return sum(window) / len(window)


def run_volatility_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    atr = compute_atr(bars)
    if atr is None:
        return {"regime": "UNKNOWN", "atr": None, "bucket": "UNKNOWN"}
    if atr < 0.0005:
        bucket = "LOW"
    elif atr < 0.0015:
        bucket = "MEDIUM"
    else:
        bucket = "HIGH"
    return {"regime": "RANGING" if bucket == "LOW" else "TRENDING", "atr": atr, "bucket": bucket}

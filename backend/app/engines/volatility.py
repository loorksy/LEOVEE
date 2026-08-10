from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class OHLCBar:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def compute_atr(bars: list[OHLCBar], period: int = 14) -> Decimal | None:
    if len(bars) < period + 1:
        return None
    trs: list[Decimal] = []
    for i in range(1, len(bars)):
        high_low = bars[i].high - bars[i].low
        high_close = abs(bars[i].high - bars[i - 1].close)
        low_close = abs(bars[i].low - bars[i - 1].close)
        trs.append(max(high_low, high_close, low_close))
    window = trs[-period:]
    return sum(window) / Decimal(len(window))


def run_volatility_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    atr = compute_atr(bars)
    if atr is None:
        return {"regime": "UNKNOWN", "atr": None, "bucket": "UNKNOWN"}
    atr_f = float(atr)
    if atr_f < 0.0005:
        bucket = "LOW"
    elif atr_f < 0.0015:
        bucket = "MEDIUM"
    else:
        bucket = "HIGH"
    return {"regime": "RANGING" if bucket == "LOW" else "TRENDING", "atr": atr_f, "bucket": bucket}

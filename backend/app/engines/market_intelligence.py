from __future__ import annotations

from typing import Any

from app.engines.volatility import OHLCBar


def run_market_intelligence_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    """
    Deterministic regime snapshot: trend, range, momentum, exhaustion (Phase 9).
    """
    if len(bars) < 5:
        return {
            "trend": "UNKNOWN",
            "range": "UNKNOWN",
            "momentum": 0.0,
            "exhaustion": False,
            "confidence": 0.0,
        }

    closes = [float(b.close) for b in bars]
    window = closes[-20:] if len(closes) >= 20 else closes
    slope = (window[-1] - window[0]) / max(len(window) - 1, 1)
    high_band = max(window)
    low_band = min(window)
    span = high_band - low_band

    if abs(slope) < span * 0.02:
        trend = "RANGE"
    elif slope > 0:
        trend = "UP"
    else:
        trend = "DOWN"

    recent_range = max(closes[-5:]) - min(closes[-5:])
    range_state = "TIGHT" if recent_range < span * 0.25 else "WIDE"

    momentum = slope / span if span > 0 else 0.0
    exhaustion = abs(momentum) > 0.8 and trend != "RANGE"

    return {
        "trend": trend,
        "range": range_state,
        "momentum": round(momentum, 4),
        "exhaustion": exhaustion,
        "confidence": min(0.9, 0.4 + abs(momentum)),
    }

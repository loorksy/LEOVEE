"""Liquidity: sweeps and equal highs/lows — real, as of M4.

Replaces the placeholder that inspected only the final bar and compared equal
highs with a fixed ``1e-5`` absolute tolerance. That tolerance was meaningless
across instruments — a fraction of a pip on EURUSD, more than a pip on a JPY
cross — and since Leovee trades gold alone (ADR 0007), the tolerance is now
derived from gold's actual pip size rather than a constant that happened to suit
one currency pair.

A sweep is a raid on resting orders: price pushes through a prior extreme and
closes back inside it. The close is what distinguishes a sweep from a break, so
it is the part the detector keys on.
"""

from __future__ import annotations

from typing import Any

from app.core.symbols import GOLD
from app.core.timeframes import MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.primitives.pivots import all_confirmed_pivots
from app.engines.status import engine_unavailable

#: Two extremes within this many pips are "equal" — the cluster that resting
#: orders actually sit on, rather than a single exact price.
EQUAL_LEVEL_PIPS = 2.0

#: How far back a sweep may reference. Beyond this the "prior extreme" is not
#: liquidity a scalp is reaching for.
SWEEP_LOOKBACK_BARS = 60


def _equal_tolerance() -> float:
    return EQUAL_LEVEL_PIPS * (10.0**GOLD.pip_location)


def run_liquidity_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    if len(bars) < MIN_CANDLES_FOR_ANALYSIS:
        return engine_unavailable("liquidity")

    tolerance = _equal_tolerance()
    window = bars[-SWEEP_LOOKBACK_BARS:]

    sweeps: list[dict[str, Any]] = []
    # Start past the first bar so there is always a prior extreme to raid.
    for i in range(1, len(window)):
        bar = window[i]
        prior = window[:i]
        prior_high = max(b.high for b in prior)
        prior_low = min(b.low for b in prior)
        # Buy-side liquidity sits above highs: price takes it, then closes back
        # below. A close that stays above is a break, not a sweep.
        if bar.high > prior_high and bar.close < prior_high:
            sweeps.append(
                {
                    "side": "BUY_SIDE",
                    "ts": bar.ts.isoformat(),
                    "level": prior_high,
                    "extreme": bar.high,
                    "penetration": bar.high - prior_high,
                }
            )
        if bar.low < prior_low and bar.close > prior_low:
            sweeps.append(
                {
                    "side": "SELL_SIDE",
                    "ts": bar.ts.isoformat(),
                    "level": prior_low,
                    "extreme": bar.low,
                    "penetration": prior_low - bar.low,
                }
            )

    pivots = all_confirmed_pivots(bars)
    equal_highs = _equal_clusters([p.price for p in pivots if p.kind == "high"], tolerance)
    equal_lows = _equal_clusters([p.price for p in pivots if p.kind == "low"], tolerance)

    return {
        "sweeps": sweeps,
        "recent_sweep": sweeps[-1] if sweeps else None,
        "equal_highs": equal_highs,
        "equal_lows": equal_lows,
        "has_equal_highs": bool(equal_highs),
        "has_equal_lows": bool(equal_lows),
        "tolerance": tolerance,
    }


def _equal_clusters(prices: list[float], tolerance: float) -> list[dict[str, Any]]:
    """Groups of two or more extremes within tolerance of each other.

    A single extreme is not equal-anything; the pattern that matters is several
    attempts stalling at the same place, because that is where the resting
    orders accumulate.
    """
    clusters: list[list[float]] = []
    for price in sorted(prices):
        if clusters and abs(clusters[-1][-1] - price) <= tolerance:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return [
        {"price": sum(group) / len(group), "count": len(group)}
        for group in clusters
        if len(group) >= 2
    ]

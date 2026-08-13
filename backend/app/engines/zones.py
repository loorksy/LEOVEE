"""Supply and demand zones — real, as of M4.

Replaces the worst placeholder in the codebase: one demand zone and one supply
zone spanning twice the last bar's range, each with a hardcoded strength of 0.5.
Those were not weak zones, they were invented ones — no imbalance, no origin, no
revisit count, no relationship to anything before the final bar — and they
reached the user as measured evidence.

A zone here is an **imbalance**: a candle whose body ran far enough that price
left an area behind without trading back through it. The zone is the origin of
that move, and its strength comes from three things that can actually be
observed — how large the departing move was relative to volatility, how many
times price has since returned to it, and how fresh it is.

A zone that price has traded straight through is consumed and is not reported.
That is the difference between a level that will hold and one that already
failed.
"""

from __future__ import annotations

from typing import Any

from app.core.timeframes import MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.primitives.indicators import atr
from app.engines.status import engine_unavailable

#: A departing move must be at least this many ATR to leave an imbalance worth
#: marking. Below it, every ordinary bar becomes a zone.
MIN_IMPULSE_ATR = 1.5

#: The most zones reported per side. Bounded output keeps the snapshot usable as
#: model context and the chart legible; an unbounded list is neither.
MAX_ZONES_PER_SIDE = 3

#: Zones older than this are dropped: on a scalp series, an untouched zone from
#: hundreds of bars ago is not what price is reacting to now.
MAX_ZONE_AGE_BARS = 240


def run_zones_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    if len(bars) < MIN_CANDLES_FOR_ANALYSIS:
        return engine_unavailable("zones")

    atr_value = atr(bars, 14)
    if atr_value is None or atr_value <= 0:
        # Without a volatility scale there is no way to say which move was
        # large enough to leave an imbalance.
        return engine_unavailable("zones")

    last_price = bars[-1].close
    candidates: list[dict[str, Any]] = []
    start = max(1, len(bars) - MAX_ZONE_AGE_BARS)

    for i in range(start, len(bars) - 1):
        bar = bars[i]
        body = abs(bar.close - bar.open)
        if body < MIN_IMPULSE_ATR * atr_value:
            continue

        bullish = bar.close > bar.open
        # The origin of the move: the base price left behind, not the whole bar.
        if bullish:
            low, high = bar.low, min(bar.open, bar.close)
            zone_type = "DEMAND"
        else:
            low, high = max(bar.open, bar.close), bar.high
            zone_type = "SUPPLY"
        if high <= low:
            continue

        following = bars[i + 1 :]
        # Traded clean through: the zone was consumed and is not a level any
        # more. This is the check the placeholder had no notion of.
        if zone_type == "DEMAND" and any(b.close < low for b in following):
            continue
        if zone_type == "SUPPLY" and any(b.close > high for b in following):
            continue

        touches = sum(1 for b in following if b.low <= high and b.high >= low)
        age = len(bars) - 1 - i
        impulse = body / atr_value

        # Three observable components, each capped so no single one dominates:
        # how decisive the departure was, how often price respected the zone,
        # and how recent it is.
        impulse_score = min(1.0, impulse / 3.0)
        touch_score = min(1.0, touches / 3.0)
        recency_score = max(0.0, 1.0 - age / MAX_ZONE_AGE_BARS)
        strength = round(0.5 * impulse_score + 0.3 * touch_score + 0.2 * recency_score, 4)

        candidates.append(
            {
                "type": zone_type,
                "low": low,
                "high": high,
                "origin_ts": bar.ts.isoformat(),
                "origin_index": i,
                "impulse_atr": round(impulse, 4),
                "touches": touches,
                "age_bars": age,
                "strength": strength,
                "distance": abs((low + high) / 2 - last_price),
            }
        )

    demand = _top(candidates, "DEMAND")
    supply = _top(candidates, "SUPPLY")
    return {
        "zones": demand + supply,
        "demand": demand,
        "supply": supply,
        "atr": atr_value,
    }


def _top(candidates: list[dict[str, Any]], zone_type: str) -> list[dict[str, Any]]:
    side = [zone for zone in candidates if zone["type"] == zone_type]
    # Strongest first, then nearest — a strong zone far away is still the more
    # important structure, but proximity breaks ties usefully for a scalp.
    side.sort(key=lambda zone: (-float(zone["strength"]), float(zone["distance"])))
    return side[:MAX_ZONES_PER_SIDE]

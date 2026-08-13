"""Swing structure: levels, clustering and trend inference.

Ported from AiChart's ``src/lib/ohlc/structure.ts``.

This replaces the placeholder that set bias by comparing the first close to the
last. The difference is not a matter of accuracy: "price ended higher than it
started" is a statement about two bars, while market structure is a statement
about the sequence of swing highs and lows between them. A series can close
higher across a clean downtrend.

Three things are worth not smoothing away in the port:

- **Levels are clustered, not listed.** Two swing highs a tick apart are one
  level touched twice, and touch count is the main strength signal. Clustering
  averages the price as it absorbs each touch, so a level drifts toward where
  price actually reacted.
- **Strength weights volume when it exists and ignores it when it does not**,
  rather than substituting a neutral value. Gold's tick volume is real but
  patchy; scoring an unknown as average would rank a level nobody traded
  alongside one that stopped a move.
- **Trend inference tolerates 0.1%.** Requiring strictly higher highs makes the
  answer flip on a single tick of noise, which on a 1-minute gold chart is most
  bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.numeric import js_round
from app.engines.bar import OHLCBar

__all__ = [
    "LevelType",
    "StructureShape",
    "DetectedLevel",
    "StructureAnalysis",
    "SWING_LOOKBACK",
    "LEVEL_TOLERANCE_PCT",
    "MAX_LEVELS",
    "detect_structure_levels",
    "level_to_dict",
]

LevelType = Literal["support", "resistance"]
StructureShape = Literal["uptrend", "downtrend", "range", "unknown"]

SWING_LOOKBACK = 2
LEVEL_TOLERANCE_PCT = 0.0008
MAX_LEVELS = 8


@dataclass(frozen=True, slots=True)
class DetectedLevel:
    price: float
    type: LevelType
    touches: int
    last_index: int
    #: Mean swing-bar volume relative to the series median (1 = typical).
    #: ``None`` when the series carries no usable volume.
    volume_score: float | None
    #: Deterministic 0–100 score from touches, relative volume and recency.
    strength_score: float


@dataclass(frozen=True, slots=True)
class StructureAnalysis:
    current_price: float
    supports: list[DetectedLevel]
    resistances: list[DetectedLevel]
    nearest_support: float | None
    nearest_resistance: float | None
    swing_highs: list[float]
    swing_lows: list[float]
    structure: StructureShape

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_price": self.current_price,
            "structure": self.structure,
            "nearest_support": self.nearest_support,
            "nearest_resistance": self.nearest_resistance,
            "swing_highs": list(self.swing_highs),
            "swing_lows": list(self.swing_lows),
            "supports": [level_to_dict(level) for level in self.supports],
            "resistances": [level_to_dict(level) for level in self.resistances],
        }


def level_to_dict(level: DetectedLevel) -> dict[str, Any]:
    return {
        "price": level.price,
        "type": level.type,
        "touches": level.touches,
        "last_index": level.last_index,
        "volume_score": level.volume_score,
        "strength_score": level.strength_score,
    }


def _round(value: float, digits: int = 4) -> float:
    factor = 10**digits
    return float(js_round(value * factor)) / float(factor)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _median_positive_volume(bars: list[OHLCBar]) -> float | None:
    values = sorted(bar.volume for bar in bars if bar.volume > 0)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def _is_swing_high(bars: list[OHLCBar], index: int, lookback: int) -> bool:
    high = bars[index].high
    for i in range(index - lookback, index + lookback + 1):
        if i == index or i < 0 or i >= len(bars):
            continue
        if bars[i].high >= high:
            return False
    return True


def _is_swing_low(bars: list[OHLCBar], index: int, lookback: int) -> bool:
    low = bars[index].low
    for i in range(index - lookback, index + lookback + 1):
        if i == index or i < 0 or i >= len(bars):
            continue
        if bars[i].low <= low:
            return False
    return True


@dataclass
class _Cluster:
    price: float
    type: LevelType
    touches: int
    last_index: int
    volume_weight_sum: float
    volume_samples: int


def _cluster_levels(
    prices: list[float],
    level_type: LevelType,
    indices: list[int],
    current_price: float,
    bars: list[OHLCBar],
) -> list[DetectedLevel]:
    baseline_volume = _median_positive_volume(bars)

    points: list[tuple[float, int, float | None]] = []
    for price, index in zip(prices, indices, strict=True):
        volume = bars[index].volume if 0 <= index < len(bars) else 0.0
        weight = volume / baseline_volume if baseline_volume is not None and volume > 0 else None
        points.append((price, index, weight))
    points.sort(key=lambda point: point[0])

    clusters: list[_Cluster] = []
    for price, index, weight in points:
        # Tolerance is relative to price, with an absolute floor so a
        # near-zero price cannot collapse every level into one.
        tol = max(price * LEVEL_TOLERANCE_PCT, 1e-8)
        existing = next((c for c in clusters if abs(c.price - price) <= tol), None)
        if existing is not None:
            existing.touches += 1
            # The level migrates toward each new touch rather than staying at
            # the first one seen.
            existing.price = (existing.price + price) / 2
            existing.last_index = max(existing.last_index, index)
            if weight is not None:
                existing.volume_weight_sum += weight
                existing.volume_samples += 1
        else:
            clusters.append(
                _Cluster(
                    price=price,
                    type=level_type,
                    touches=1,
                    last_index=index,
                    volume_weight_sum=weight or 0.0,
                    volume_samples=0 if weight is None else 1,
                )
            )

    max_touches = max([1, *[c.touches for c in clusters]])
    scored: list[DetectedLevel] = []
    for cluster in clusters:
        volume_score = (
            cluster.volume_weight_sum / cluster.volume_samples
            if cluster.volume_samples > 0
            else None
        )
        touch_component = _clamp01(cluster.touches / max_touches)
        recency_component = _clamp01(cluster.last_index / (len(bars) - 1)) if len(bars) > 1 else 0.0
        if volume_score is None:
            # No volume evidence: score on touches alone rather than assuming
            # an average level of interest.
            strength = 100 * touch_component
        else:
            strength = 100 * (
                0.55 * touch_component
                + 0.30 * _clamp01(volume_score / 2)
                + 0.15 * recency_component
            )
        scored.append(
            DetectedLevel(
                price=cluster.price,
                type=cluster.type,
                touches=cluster.touches,
                last_index=cluster.last_index,
                volume_score=None if volume_score is None else _round(volume_score),
                strength_score=_round(strength, 2),
            )
        )

    def sort_key(level: DetectedLevel) -> tuple[float, float, float]:
        distance = abs(level.price - current_price)
        # With volume available, strength leads; without it, touch count does,
        # and proximity to price breaks the remaining ties.
        primary = -level.strength_score if baseline_volume is not None else 0.0
        return (primary, -level.touches, distance)

    scored.sort(key=sort_key)
    return scored[:MAX_LEVELS]


def _infer_structure(swing_highs: list[float], swing_lows: list[float]) -> StructureShape:
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "unknown"

    recent_highs = swing_highs[-3:]
    recent_lows = swing_lows[-3:]

    # 0.1% tolerance: strict comparisons flip on a single tick, which on a
    # 1-minute gold chart is most bars.
    higher_highs = all(
        h >= recent_highs[i - 1] * 0.999 for i, h in enumerate(recent_highs) if i > 0
    )
    higher_lows = all(
        low >= recent_lows[i - 1] * 0.999 for i, low in enumerate(recent_lows) if i > 0
    )
    if higher_highs and higher_lows:
        return "uptrend"

    lower_highs = all(h <= recent_highs[i - 1] * 1.001 for i, h in enumerate(recent_highs) if i > 0)
    lower_lows = all(
        low <= recent_lows[i - 1] * 1.001 for i, low in enumerate(recent_lows) if i > 0
    )
    if lower_highs and lower_lows:
        return "downtrend"

    high_range = max(recent_highs) - min(recent_highs)
    low_range = max(recent_lows) - min(recent_lows)
    average = (recent_highs[-1] + recent_lows[-1]) / 2
    if average > 0 and (high_range + low_range) / average < 0.01:
        return "range"

    return "unknown"


def detect_structure_levels(bars: list[OHLCBar]) -> StructureAnalysis:
    """Swing-based support and resistance, plus the structural shape."""
    if len(bars) < SWING_LOOKBACK * 2 + 3:
        return StructureAnalysis(
            current_price=bars[-1].close if bars else 0.0,
            supports=[],
            resistances=[],
            nearest_support=None,
            nearest_resistance=None,
            swing_highs=[],
            swing_lows=[],
            structure="unknown",
        )

    swing_highs: list[float] = []
    swing_high_idx: list[int] = []
    swing_lows: list[float] = []
    swing_low_idx: list[int] = []

    for i in range(SWING_LOOKBACK, len(bars) - SWING_LOOKBACK):
        if _is_swing_high(bars, i, SWING_LOOKBACK):
            swing_highs.append(bars[i].high)
            swing_high_idx.append(i)
        if _is_swing_low(bars, i, SWING_LOOKBACK):
            swing_lows.append(bars[i].low)
            swing_low_idx.append(i)

    current_price = bars[-1].close
    resistances = _cluster_levels(swing_highs, "resistance", swing_high_idx, current_price, bars)
    supports = _cluster_levels(swing_lows, "support", swing_low_idx, current_price, bars)

    below = sorted(
        (level for level in supports if level.price <= current_price),
        key=lambda level: -level.price,
    )
    above = sorted(
        (level for level in resistances if level.price >= current_price),
        key=lambda level: level.price,
    )

    return StructureAnalysis(
        current_price=current_price,
        supports=supports,
        resistances=resistances,
        nearest_support=below[0].price if below else None,
        nearest_resistance=above[0].price if above else None,
        swing_highs=swing_highs[-6:],
        swing_lows=swing_lows[-6:],
        structure=_infer_structure(swing_highs, swing_lows),
    )

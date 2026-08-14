"""Numeric market-regime classifier — trending, ranging, volatile, illiquid.

Ported from AiChart's ``ohlc/marketRegime.ts``. Nothing here reads a clock, an
LLM or any state outside the bars it is handed.

**Everything is normalised against the instrument's own recent behaviour.** An
ATR of 3.20 on gold means nothing on its own; ATR at 1.8x its own 60-bar median
means volatility has expanded. This is why the classifier compares each measure
to a baseline drawn from the same series rather than to a constant, and it is
what lets one rule work across a quiet Asian session and a payrolls release.

**The rule priority is deliberate, not incidental.** An exceptional volatility
expansion is reported before trend, then a well-covered volume collapse, then
ADX trend, and everything else with sufficient data is a range. The order
encodes which fact most changes how a position should be sized: a trend read
during a volatility blowout is a trend you will be stopped out of.

Baselines use the **median**, not the mean. One payrolls candle drags a mean far
enough that the bar after it looks calm by comparison, which is precisely
backwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from app.engines.bar import OHLCBar
from app.engines.primitives.indicators import directional_movement

__all__ = [
    "MARKET_REGIME_THRESHOLDS",
    "RegimeThresholds",
    "MarketRegimeMetrics",
    "MarketRegimeAnalysis",
    "detect_market_regime",
]

_EPSILON = 1e-12
#: The baseline window: the 60 completed observations before the current one.
_BASELINE_WINDOW = 61


@dataclass(frozen=True, slots=True)
class RegimeThresholds:
    minimum_candles: int = 60
    adx_trending_minimum: float = 25.0
    directional_spread_minimum: float = 5.0
    high_atr_ratio: float = 1.5
    high_bollinger_bandwidth_ratio: float = 1.35
    extreme_volatility_ratio: float = 2.0
    low_volume_ratio: float = 0.55
    minimum_volume_coverage: float = 0.8

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_candles": self.minimum_candles,
            "adx_trending_minimum": self.adx_trending_minimum,
            "directional_spread_minimum": self.directional_spread_minimum,
            "high_atr_ratio": self.high_atr_ratio,
            "high_bollinger_bandwidth_ratio": self.high_bollinger_bandwidth_ratio,
            "extreme_volatility_ratio": self.extreme_volatility_ratio,
            "low_volume_ratio": self.low_volume_ratio,
            "minimum_volume_coverage": self.minimum_volume_coverage,
        }


MARKET_REGIME_THRESHOLDS = RegimeThresholds()


@dataclass(frozen=True, slots=True)
class MarketRegimeMetrics:
    atr14: float | None = None
    atr_percent: float | None = None
    atr_baseline_percent: float | None = None
    atr_ratio: float | None = None
    adx14: float | None = None
    plus_di14: float | None = None
    minus_di14: float | None = None
    bollinger_bandwidth: float | None = None
    bollinger_baseline_bandwidth: float | None = None
    bollinger_bandwidth_ratio: float | None = None
    recent_average_volume: float | None = None
    baseline_average_volume: float | None = None
    volume_ratio: float | None = None
    volume_coverage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "atr14": self.atr14,
            "atr_percent": self.atr_percent,
            "atr_baseline_percent": self.atr_baseline_percent,
            "atr_ratio": self.atr_ratio,
            "adx14": self.adx14,
            "plus_di14": self.plus_di14,
            "minus_di14": self.minus_di14,
            "bollinger_bandwidth": self.bollinger_bandwidth,
            "bollinger_baseline_bandwidth": self.bollinger_baseline_bandwidth,
            "bollinger_bandwidth_ratio": self.bollinger_bandwidth_ratio,
            "recent_average_volume": self.recent_average_volume,
            "baseline_average_volume": self.baseline_average_volume,
            "volume_ratio": self.volume_ratio,
            "volume_coverage": self.volume_coverage,
        }


@dataclass(frozen=True, slots=True)
class MarketRegimeAnalysis:
    regime: str  # trending | ranging | high_volatility | low_liquidity | unknown
    trend_direction: str  # bullish | bearish | neutral
    candle_count: int
    metrics: MarketRegimeMetrics
    trending: bool
    high_volatility: bool
    low_liquidity: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def is_known(self) -> bool:
        return self.regime != "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "trend_direction": self.trend_direction,
            "candle_count": self.candle_count,
            "metrics": self.metrics.to_dict(),
            "signals": {
                "trending": self.trending,
                "high_volatility": self.high_volatility,
                "low_liquidity": self.low_liquidity,
            },
            "reasons": list(self.reasons),
            "thresholds": MARKET_REGIME_THRESHOLDS.to_dict(),
        }


def _round(value: float | None, digits: int = 8) -> float | None:
    if value is None or not isfinite(value):
        return None
    return round(value, digits)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _ratio(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or abs(baseline) <= _EPSILON:
        return None
    return current / baseline


def _unknown(candle_count: int, reason: str) -> MarketRegimeAnalysis:
    return MarketRegimeAnalysis(
        regime="unknown",
        trend_direction="neutral",
        candle_count=candle_count,
        metrics=MarketRegimeMetrics(),
        trending=False,
        high_volatility=False,
        low_liquidity=False,
        reasons=[reason],
    )


def _is_valid(candle: OHLCBar) -> bool:
    values = (candle.open, candle.high, candle.low, candle.close)
    if not all(isfinite(v) and v > 0 for v in values):
        return False
    return candle.high >= max(candle.open, candle.close, candle.low) and candle.low <= min(
        candle.open, candle.close, candle.high
    )


def _true_range_series(bars: list[OHLCBar]) -> list[float]:
    return [
        max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        for i in range(1, len(bars))
    ]


def _atr_series(bars: list[OHLCBar], period: int = 14) -> list[float]:
    """Wilder ATR at every bar that has one, oldest first."""
    trs = _true_range_series(bars)
    if len(trs) < period:
        return []
    value = sum(trs[:period]) / period
    out = [value]
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
        out.append(value)
    return out


def _aligned_percent(values: list[float], closes: list[float]) -> list[float]:
    """Each value as a share of the close it belongs to, right-aligned."""
    offset = len(closes) - len(values)
    out: list[float] = []
    for index, value in enumerate(values):
        position = offset + index
        if 0 <= position < len(closes) and closes[position] > 0 and isfinite(value):
            out.append(value / closes[position])
    return out


def _bandwidth_series(closes: list[float], period: int = 20, mult: float = 2.0) -> list[float]:
    """Bollinger bandwidth at every bar that has one, oldest first.

    Population sigma, matching the reference: the window *is* the population
    here, not a sample drawn from one.
    """
    out: list[float] = []
    for end in range(period, len(closes) + 1):
        window = closes[end - period : end]
        middle = sum(window) / period
        if abs(middle) <= _EPSILON:
            continue
        variance = sum((value - middle) ** 2 for value in window) / period
        sigma = variance**0.5
        out.append((2 * mult * sigma) / abs(middle))
    return out


def _volume_metrics(bars: list[OHLCBar]) -> tuple[float | None, float | None, float | None, float]:
    window = bars[-60:]
    usable = [b.volume for b in window if isfinite(b.volume) and b.volume > 0]
    coverage = len(usable) / len(window) if window else 0.0
    recent = [b.volume for b in window[-10:] if isfinite(b.volume) and b.volume > 0]
    baseline = [b.volume for b in window[:-10] if isfinite(b.volume) and b.volume > 0]
    recent_mean = _mean(recent)
    baseline_mean = _mean(baseline)
    return (
        _round(recent_mean, 4),
        _round(baseline_mean, 4),
        _round(_ratio(recent_mean, baseline_mean), 6),
        _round(coverage, 4) or 0.0,
    )


def detect_market_regime(
    bars: list[OHLCBar], thresholds: RegimeThresholds = MARKET_REGIME_THRESHOLDS
) -> MarketRegimeAnalysis:
    if len(bars) < thresholds.minimum_candles:
        return _unknown(len(bars), "insufficient_candles")
    if not all(_is_valid(candle) for candle in bars):
        # A malformed candle poisons every measure downstream, and a regime read
        # off bad bars is worse than no regime: it looks exactly like a good one.
        return _unknown(len(bars), "invalid_candles")

    closes = [b.close for b in bars]

    atr_values = _atr_series(bars)
    atr14 = atr_values[-1] if atr_values else None
    atr_percent_series = _aligned_percent(atr_values, closes)
    atr_percent = atr_percent_series[-1] if atr_percent_series else None
    atr_baseline_percent = _median(atr_percent_series[-_BASELINE_WINDOW:-1])
    atr_ratio = _ratio(atr_percent, atr_baseline_percent)

    dmi = directional_movement(bars)

    bandwidths = _bandwidth_series(closes)
    bandwidth = bandwidths[-1] if bandwidths else None
    bandwidth_baseline = _median(bandwidths[-_BASELINE_WINDOW:-1])
    bandwidth_ratio = _ratio(bandwidth, bandwidth_baseline)

    if (
        atr14 is None
        or atr_percent is None
        or atr_baseline_percent is None
        or atr_ratio is None
        or dmi is None
        or bandwidth is None
        or bandwidth_baseline is None
        or bandwidth_ratio is None
    ):
        return _unknown(len(bars), "indicator_calculation_failed")

    recent_volume, baseline_volume, volume_ratio, coverage = _volume_metrics(bars)

    trending = (
        dmi.adx >= thresholds.adx_trending_minimum
        and dmi.spread >= thresholds.directional_spread_minimum
    )
    high_volatility = (
        (
            atr_ratio >= thresholds.high_atr_ratio
            and bandwidth_ratio >= thresholds.high_bollinger_bandwidth_ratio
        )
        or atr_ratio >= thresholds.extreme_volatility_ratio
        or bandwidth_ratio >= thresholds.extreme_volatility_ratio
    )
    # Thin volume only counts as illiquidity when we actually have volume to
    # read, and never during an expansion — a fast market on light reported
    # volume is a fast market, not a quiet one.
    low_liquidity = (
        coverage >= thresholds.minimum_volume_coverage
        and volume_ratio is not None
        and volume_ratio <= thresholds.low_volume_ratio
        and not high_volatility
    )

    if dmi.spread < thresholds.directional_spread_minimum:
        trend_direction = "neutral"
    else:
        trend_direction = "bullish" if dmi.plus_di > dmi.minus_di else "bearish"

    if high_volatility:
        regime, reason = "high_volatility", "normalized_volatility_expansion"
    elif low_liquidity:
        regime, reason = "low_liquidity", "recent_volume_contraction"
    elif trending:
        regime, reason = "trending", "adx_directional_trend"
    else:
        regime, reason = "ranging", "no_trend_or_volatility_expansion"

    return MarketRegimeAnalysis(
        regime=regime,
        trend_direction=trend_direction,
        candle_count=len(bars),
        metrics=MarketRegimeMetrics(
            atr14=_round(atr14),
            atr_percent=_round(atr_percent, 10),
            atr_baseline_percent=_round(atr_baseline_percent, 10),
            atr_ratio=_round(atr_ratio, 6),
            adx14=_round(dmi.adx, 6),
            plus_di14=_round(dmi.plus_di, 6),
            minus_di14=_round(dmi.minus_di, 6),
            bollinger_bandwidth=_round(bandwidth, 10),
            bollinger_baseline_bandwidth=_round(bandwidth_baseline, 10),
            bollinger_bandwidth_ratio=_round(bandwidth_ratio, 6),
            recent_average_volume=recent_volume,
            baseline_average_volume=baseline_volume,
            volume_ratio=volume_ratio,
            volume_coverage=coverage,
        ),
        trending=trending,
        high_volatility=high_volatility,
        low_liquidity=low_liquidity,
        reasons=[reason],
    )

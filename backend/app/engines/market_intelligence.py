"""Market intelligence — the regime the analysis is happening inside.

Real, as of M4. Replaces a placeholder that classified trend by comparing the
first close of a 20-bar window to the last and reported a confidence of
``0.4 + |momentum|`` — a number with no relationship to anything measured. The
danger was never that it was crude; it was that it was *confident*, and the
figure travelled to the user indistinguishable from a real one.

The classification is in ``app/engines/primitives/regime.py``. This is the
engine-shaped wrapper, plus the one thing the primitive deliberately does not
do: turn the regime into an operational stance.

**Regime is not a signal.** It never says buy or sell. It says how much to trust
a directional read and how wide the plan has to be to survive: the same
structure means a different trade at 1.8x normal volatility than at 0.8x, and a
scalp that ignores the difference is sized for a market that is not there.
"""

from __future__ import annotations

from typing import Any

from app.core.timeframes import MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import OHLCBar
from app.engines.primitives.regime import detect_market_regime
from app.engines.status import INSUFFICIENT_DATA, engine_unavailable

__all__ = ["run_market_intelligence_engine", "STANCE_BY_REGIME"]

#: What each regime means for how a plan should be built. Not a direction.
STANCE_BY_REGIME: dict[str, str] = {
    "trending": "TREND_FOLLOWING",
    "ranging": "MEAN_REVERTING",
    # Wide stops or no trade: a correct direction still loses when the noise
    # band is wider than the invalidation.
    "high_volatility": "DEFENSIVE",
    # Thin books mean the level you see is not the level you get.
    "low_liquidity": "DEFENSIVE",
}

#: Confidence in the *regime call*, not in any trade. Derived from how far the
#: deciding measure cleared its threshold, so it moves with the evidence.
_BASE_CONFIDENCE = 0.5
_MAX_CONFIDENCE = 0.9


def _regime_confidence(analysis: Any) -> float:
    metrics = analysis.metrics
    if analysis.regime == "trending":
        adx = metrics.adx14 or 0.0
        margin = max(0.0, adx - 25) / 25
    elif analysis.regime == "high_volatility":
        ratio = max(metrics.atr_ratio or 0.0, metrics.bollinger_bandwidth_ratio or 0.0)
        margin = max(0.0, ratio - 1.5) / 1.5
    elif analysis.regime == "low_liquidity":
        margin = max(0.0, 0.55 - (metrics.volume_ratio or 0.55)) / 0.55
    else:
        # Ranging is the residual class, and a residual is a weaker claim than a
        # measurement: it is what is left when nothing else fired.
        adx = metrics.adx14 or 0.0
        margin = max(0.0, 25 - adx) / 25
    return round(min(_MAX_CONFIDENCE, _BASE_CONFIDENCE + margin * 0.4), 4)


def run_market_intelligence_engine(bars: list[OHLCBar]) -> dict[str, Any]:
    if len(bars) < MIN_CANDLES_FOR_ANALYSIS:
        return engine_unavailable("market_intelligence", INSUFFICIENT_DATA)

    analysis = detect_market_regime(bars)
    if not analysis.is_known:
        # `unknown` carries its own reason (too few bars, malformed candles, an
        # indicator that could not be computed). Passing it off as "ranging"
        # would turn a data problem into a market claim.
        return engine_unavailable(
            "market_intelligence", INSUFFICIENT_DATA, detail=analysis.reasons[0]
        )

    payload = analysis.to_dict()
    payload["stance"] = STANCE_BY_REGIME[analysis.regime]
    payload["confidence"] = _regime_confidence(analysis)
    # `trend` is the vocabulary the rest of the pipeline already reads. It is
    # deliberately *not* a plain alias of `trend_direction`: the directional
    # lean is computed from the DI spread whatever the regime, so a range with a
    # mild upward tilt has a bullish lean — and publishing that as "trend" is
    # how a consumer ends up trading a trend that was never claimed. Outside a
    # trending regime the trend is NEUTRAL, and the raw lean stays available
    # under `trend_direction` for anyone who wants it.
    payload["trend"] = (
        analysis.trend_direction.upper() if analysis.regime == "trending" else "NEUTRAL"
    )
    return payload

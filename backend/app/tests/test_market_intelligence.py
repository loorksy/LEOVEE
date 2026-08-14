"""Market intelligence: the regime, measured against the instrument's own past.

These replace tests written against the placeholder's invented vocabulary
(`momentum`, `range: TIGHT|WIDE`, a confidence of `0.4 + |momentum|`). None of
those fields described anything that was measured, so there was nothing in them
worth preserving.
"""

from __future__ import annotations

import pytest

from app.engines.bar import OHLCBar
from app.engines.market_intelligence import STANCE_BY_REGIME, run_market_intelligence_engine
from app.engines.status import INSUFFICIENT_DATA, is_unavailable
from app.tests.bars import path_bars, rising_bars, swinging_bars

pytestmark = pytest.mark.no_db


def _trending() -> list[OHLCBar]:
    return swinging_bars(14, drift=6.0, swing=9.0, bars_per_leg=5)


def _ranging() -> list[OHLCBar]:
    turns: list[float] = []
    for _ in range(12):
        turns.extend([2000.0, 2012.0])
    return path_bars(turns, bars_per_leg=5)


def test_a_directional_market_is_classified_as_trending() -> None:
    result = run_market_intelligence_engine(_trending())
    assert result["regime"] == "trending"
    assert result["trend"] == "BULLISH"
    assert result["stance"] == "TREND_FOLLOWING"
    assert result["reasons"] == ["adx_directional_trend"]


def test_an_oscillating_market_is_classified_as_ranging() -> None:
    result = run_market_intelligence_engine(_ranging())
    assert result["regime"] == "ranging"
    assert result["stance"] == "MEAN_REVERTING"


def test_a_ranging_market_reports_no_trend_even_with_a_directional_lean() -> None:
    """The lean is not the trend, and publishing it as one invents a claim.

    +DI/-DI are computed whatever the regime, so an oscillation with a mild
    upward tilt has a bullish lean. A consumer reading `trend` would trade a
    trend nothing measured. The raw lean stays under `trend_direction`.
    """
    result = run_market_intelligence_engine(_ranging())
    assert result["trend"] == "NEUTRAL"
    assert result["trend_direction"] in ("bullish", "bearish", "neutral")


def test_every_regime_has_a_stance_and_none_of_them_is_a_direction() -> None:
    """Regime says how to build the plan, never which way to trade."""
    assert set(STANCE_BY_REGIME) == {"trending", "ranging", "high_volatility", "low_liquidity"}
    assert not {"BUY", "SELL", "BULLISH", "BEARISH"} & set(STANCE_BY_REGIME.values())


def test_too_few_bars_declines_and_says_so_is_a_data_problem() -> None:
    """An implemented engine short of data must not read as an unported one."""
    result = run_market_intelligence_engine(rising_bars(25))
    assert is_unavailable(result)
    assert result["reason"] == INSUFFICIENT_DATA


def test_malformed_candles_decline_rather_than_classify() -> None:
    """A regime read off bad bars looks exactly like one read off good bars."""
    bars = _trending()
    broken = bars[:-1] + [
        OHLCBar(ts=bars[-1].ts, open=2000.0, high=1990.0, low=2010.0, close=2000.0, volume=1.0)
    ]
    result = run_market_intelligence_engine(broken)
    assert is_unavailable(result)
    assert result["detail"] == "invalid_candles"


def test_confidence_tracks_the_margin_over_the_deciding_threshold() -> None:
    """Confidence in the regime call, not in any trade — and it must move."""
    strong = run_market_intelligence_engine(rising_bars(200, step=0.5, spread=0.1))
    ranging = run_market_intelligence_engine(_ranging())
    assert strong["confidence"] > ranging["confidence"]
    assert 0.5 <= ranging["confidence"] <= 0.9

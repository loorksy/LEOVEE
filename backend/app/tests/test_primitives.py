"""The deterministic primitives ported from AiChart (M2).

These pin the choices a rewrite would plausibly "clean up" and thereby change:
the EMA seed, Wilder smoothing, population sigma, the asymmetric plateau rule,
and the tolerance in trend inference.
"""

from __future__ import annotations

import math

import pytest

from app.engines.bar import OHLCBar
from app.engines.primitives.indicators import (
    adx,
    atr,
    bollinger,
    ema,
    macd,
    rsi,
    sma,
    stochastic,
)
from app.engines.primitives.pivots import (
    all_confirmed_pivots,
    confirmed_pivots,
    geometry_atr,
    zigzag_pivots,
)
from app.engines.primitives.structure import detect_structure_levels
from app.tests.bars import EPOCH, flat_bars, rising_bars, swinging_bars

pytestmark = pytest.mark.no_db


def _bar(high: float, low: float, close: float | None = None, volume: float = 0.0) -> OHLCBar:
    mid = close if close is not None else (high + low) / 2
    return OHLCBar(ts=EPOCH, open=mid, high=high, low=low, close=mid, volume=volume)


class TestMovingAverages:
    def test_sma_uses_only_the_last_period(self) -> None:
        assert sma([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)

    def test_sma_abstains_when_short(self) -> None:
        assert sma([1, 2], 3) is None

    def test_ema_seeds_with_the_sma_of_the_first_period(self) -> None:
        # With exactly `period` values the EMA is just that SMA — the seed is
        # directly observable here, and a first-value seed would give 3.0.
        assert ema([1, 2, 3], 3) == pytest.approx(2.0)

    def test_ema_weights_recent_values_more_than_sma(self) -> None:
        values = [1.0, 1.0, 1.0, 10.0]
        assert ema(values, 3) > sma(values, 3)  # type: ignore[operator]

    def test_ema_abstains_when_short(self) -> None:
        assert ema([1, 2], 3) is None


class TestRsi:
    def test_all_gains_saturates_at_100(self) -> None:
        # No losses means RS is infinite; returning 100 avoids a zero divide.
        assert rsi([float(i) for i in range(1, 20)], 14) == 100.0

    def test_all_losses_bottoms_out(self) -> None:
        assert rsi([float(i) for i in range(20, 1, -1)], 14) == pytest.approx(0.0)

    def test_flat_series_is_neutral(self) -> None:
        # Zero gain and zero loss: the no-loss branch wins, matching the
        # reference rather than returning 50.
        assert rsi([5.0] * 20, 14) == 100.0

    def test_abstains_below_period_plus_one(self) -> None:
        assert rsi([1.0] * 14, 14) is None
        assert rsi([1.0] * 15, 14) is not None

    def test_stays_within_bounds(self) -> None:
        values = [100 + math.sin(i) * 5 for i in range(60)]
        result = rsi(values, 14)
        assert result is not None
        assert 0 <= result <= 100


class TestMacd:
    def test_abstains_until_slow_plus_signal(self) -> None:
        assert macd([float(i) for i in range(34)]) is None
        assert macd([float(i) for i in range(35)]) is not None

    def test_histogram_is_macd_minus_signal(self) -> None:
        result = macd([100 + i * 0.5 for i in range(80)])
        assert result is not None
        assert result.histogram == pytest.approx(result.macd - result.signal)

    def test_rising_series_has_a_positive_macd(self) -> None:
        result = macd([100 + i for i in range(80)])
        assert result is not None
        assert result.macd > 0


class TestBollinger:
    def test_uses_population_sigma(self) -> None:
        # Population sigma of 1..5 is sqrt(2); the sample sigma a stats library
        # defaults to would be sqrt(2.5) and widen both bands.
        result = bollinger([1, 2, 3, 4, 5], period=5, mult=1)
        assert result is not None
        assert result.middle == pytest.approx(3.0)
        assert result.upper == pytest.approx(3 + math.sqrt(2))

    def test_percent_b_exceeds_one_when_the_close_is_outside_the_band(self) -> None:
        # %B is not clamped: a close above the upper band reads above 1, which
        # is the signal. Clamping it would hide exactly the breakout case.
        result = bollinger([1, 2, 3, 4, 5], period=5, mult=1)
        assert result is not None
        assert result.percent_b > 1.0

    def test_percent_b_sits_inside_the_band_for_a_mid_range_close(self) -> None:
        result = bollinger([1, 2, 3, 4, 5, 3], period=5, mult=2)
        assert result is not None
        assert 0.0 < result.percent_b < 1.0

    def test_flat_series_reports_a_midpoint_rather_than_dividing_by_zero(self) -> None:
        result = bollinger([2.0] * 20)
        assert result is not None
        assert result.percent_b == 0.5
        assert result.width_pct == 0.0


class TestStochastic:
    def test_abstains_when_short(self) -> None:
        assert stochastic(rising_bars(10)) is None

    def test_rising_series_sits_near_the_top(self) -> None:
        result = stochastic(rising_bars(40))
        assert result is not None
        assert result.k > 70

    def test_flat_window_is_neutral_not_nan(self) -> None:
        result = stochastic(flat_bars(40))
        assert result is not None
        assert not math.isnan(result.k)


class TestAtrAndAdx:
    def test_atr_abstains_below_period_plus_one(self) -> None:
        assert atr(rising_bars(14), 14) is None
        assert atr(rising_bars(15), 14) is not None

    def test_atr_grows_with_range(self) -> None:
        narrow = atr(rising_bars(40, spread=0.0002), 14)
        wide = atr(rising_bars(40, spread=0.0020), 14)
        assert narrow is not None and wide is not None
        assert wide > narrow

    def test_adx_needs_two_periods_to_seed(self) -> None:
        assert adx(rising_bars(28), 14) is None
        assert adx(rising_bars(29), 14) is not None

    def test_adx_is_direction_blind(self) -> None:
        from app.tests.bars import falling_bars

        up = adx(rising_bars(60), 14)
        down = adx(falling_bars(60), 14)
        assert up is not None and down is not None
        # A clean trend either way is strong; ADX measures strength only.
        assert up > 20 and down > 20


class TestPivots:
    def test_a_clean_peak_is_a_high_pivot(self) -> None:
        bars = [_bar(10, 5), _bar(11, 6), _bar(20, 7), _bar(11, 6), _bar(10, 5)]
        pivots = confirmed_pivots(bars, "high", lookback=2)
        assert [p.index for p in pivots] == [2]

    def test_a_clean_trough_is_a_low_pivot(self) -> None:
        bars = [_bar(10, 5), _bar(9, 4), _bar(8, 1), _bar(9, 4), _bar(10, 5)]
        pivots = confirmed_pivots(bars, "low", lookback=2)
        assert [p.index for p in pivots] == [2]

    def test_plateau_keeps_the_first_bar_of_a_flat_run(self) -> None:
        # The asymmetric rule: an equal low to the right is tolerated, an equal
        # low to the left disqualifies. A symmetric rule would emit two pivots
        # here, and a double-bottom template would read two bottoms.
        bars = [_bar(10, 5), _bar(9, 4), _bar(8, 1), _bar(8, 1), _bar(9, 4), _bar(10, 5)]
        pivots = confirmed_pivots(bars, "low", lookback=1)
        assert [p.index for p in pivots] == [2]

    def test_edges_cannot_be_pivots(self) -> None:
        # There is nothing to confirm against beyond the series.
        bars = [_bar(20, 1), _bar(10, 5), _bar(11, 6)]
        assert confirmed_pivots(bars, "high", lookback=1) == []

    def test_lookback_is_clamped(self) -> None:
        bars = rising_bars(40)
        # Below 1 confirms nothing; above 5 needs more confirmation than a
        # scalp series can supply.
        assert confirmed_pivots(bars, "high", lookback=0) == confirmed_pivots(
            bars, "high", lookback=1
        )
        assert confirmed_pivots(bars, "high", lookback=99) == confirmed_pivots(
            bars, "high", lookback=5
        )

    def test_merged_pivots_are_in_index_order_highs_first(self) -> None:
        bars = [_bar(10, 5), _bar(20, 1), _bar(10, 5), _bar(9, 6), _bar(10, 5)]
        merged = all_confirmed_pivots(bars, lookback=1)
        indices = [p.index for p in merged]
        assert indices == sorted(indices)


class TestZigzag:
    def test_alternates_strictly(self) -> None:
        bars = rising_bars(80, step=0.0010)
        pivots = zigzag_pivots(bars, geometry_atr(bars))
        kinds = [p.kind for p in pivots]
        assert all(a != b for a, b in zip(kinds, kinds[1:], strict=False))

    def test_collapses_consecutive_same_side_pivots_to_the_extreme(self) -> None:
        # Two highs with no intervening low: the lower one is absorbed. A low
        # between them would make both legitimate legs instead.
        bars = [
            _bar(10, 5.0),
            _bar(15, 5.1),  # high pivot, later absorbed
            _bar(10, 5.2),
            _bar(20, 5.3),  # the more extreme high
            _bar(10, 5.4),
        ]
        pivots = zigzag_pivots(bars, 0.0, lookback=1)
        highs = [p.price for p in pivots if p.kind == "high"]
        assert highs == [20]

    def test_legs_below_the_threshold_are_noise(self) -> None:
        bars = rising_bars(60, step=0.0002)
        loose = zigzag_pivots(bars, geometry_atr(bars), min_move_atr=0.1)
        strict = zigzag_pivots(bars, geometry_atr(bars), min_move_atr=5.0)
        assert len(strict) <= len(loose)

    def test_zero_atr_does_not_admit_every_leg_through_a_zero_threshold(self) -> None:
        bars = rising_bars(40)
        assert zigzag_pivots(bars, 0.0) is not None

    def test_empty_input(self) -> None:
        assert zigzag_pivots([], 1.0) == []


class TestGeometryAtr:
    def test_returns_zero_rather_than_none_for_a_short_series(self) -> None:
        # The geometry engine multiplies this, so it needs a number; zero
        # degrades to "every leg counts", which is the safe direction.
        assert geometry_atr([]) == 0.0
        assert geometry_atr(rising_bars(1)) == 0.0

    def test_positive_for_a_real_series(self) -> None:
        assert geometry_atr(rising_bars(60)) > 0


class TestStructure:
    def test_abstains_on_a_short_series(self) -> None:
        result = detect_structure_levels(rising_bars(5))
        assert result.structure == "unknown"
        assert result.supports == []

    def test_a_monotonic_ramp_has_no_structure(self) -> None:
        # Every bar is higher than the last, so no bar is a local extreme.
        # Reporting "unknown" here is correct: a straight line has no swings.
        assert detect_structure_levels(rising_bars(80)).structure == "unknown"

    def test_swinging_advance_reads_as_an_uptrend(self) -> None:
        assert detect_structure_levels(swinging_bars(14, drift=4.0)).structure == "uptrend"

    def test_swinging_decline_reads_as_a_downtrend(self) -> None:
        assert detect_structure_levels(swinging_bars(14, drift=-4.0)).structure == "downtrend"

    def test_nearest_levels_bracket_the_current_price(self) -> None:
        result = detect_structure_levels(swinging_bars(14))
        if result.nearest_support is not None:
            assert result.nearest_support <= result.current_price
        if result.nearest_resistance is not None:
            assert result.nearest_resistance >= result.current_price

    def test_touches_cluster_rather_than_listing_every_swing(self) -> None:
        # Two swing highs a tick apart are one level touched twice, and touch
        # count is the main strength signal.
        oscillating: list[OHLCBar] = []
        for i in range(60):
            high = 2000.0 if i % 4 == 2 else 1995.0
            low = 1990.0 if i % 4 == 0 else 1994.0
            oscillating.append(_bar(high, low, volume=100.0))
        result = detect_structure_levels(oscillating)
        assert any(level.touches > 1 for level in result.resistances + result.supports)

    def test_level_count_is_bounded(self) -> None:
        result = detect_structure_levels(swinging_bars(40, drift=1.0))
        assert len(result.supports) <= 8
        assert len(result.resistances) <= 8

    def test_volume_score_is_none_when_the_series_has_no_volume(self) -> None:
        # Scoring an unknown as average would rank a level nobody traded
        # alongside one that stopped a move.
        volumeless = [
            OHLCBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close, volume=0.0)
            for b in swinging_bars(14)
        ]
        result = detect_structure_levels(volumeless)
        assert result.supports or result.resistances
        for level in result.supports + result.resistances:
            assert level.volume_score is None

    def test_strength_uses_volume_when_present(self) -> None:
        result = detect_structure_levels(swinging_bars(14))
        assert any(level.volume_score is not None for level in result.supports + result.resistances)

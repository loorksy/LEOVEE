"""Scalp-only, agent-chosen timeframes."""

from __future__ import annotations

import pytest

from app.core.timeframes import (
    ACTIVE_TIMEFRAMES,
    ANALYSIS_WINDOW_BARS,
    CONTEXT_TIMEFRAMES,
    DECISION_TIMEFRAMES,
    DEFAULT_SERIES_TIMEFRAME,
    MIN_CANDLES_FOR_ANALYSIS,
    MTF_CONTEXT_STACK,
    MTF_CONTEXT_STACK_CODES,
    is_active_timeframe,
    is_decision_timeframe,
)
from app.models.enums import Timeframe

pytestmark = pytest.mark.no_db


def test_decisions_are_scalp_frames_only() -> None:
    assert DECISION_TIMEFRAMES == (Timeframe.M1, Timeframe.M5, Timeframe.M15)


@pytest.mark.parametrize("timeframe", [Timeframe.M1, Timeframe.M5, Timeframe.M15])
def test_scalp_frames_may_carry_a_decision(timeframe: Timeframe) -> None:
    assert is_decision_timeframe(timeframe)


@pytest.mark.parametrize("timeframe", [Timeframe.M30, Timeframe.H1, Timeframe.H4, Timeframe.D1])
def test_slower_frames_may_not(timeframe: Timeframe) -> None:
    # A recommendation on H1 is a different trade, not a slower view of a scalp.
    assert not is_decision_timeframe(timeframe)


def test_context_frames_are_not_decision_frames() -> None:
    assert not set(CONTEXT_TIMEFRAMES) & set(DECISION_TIMEFRAMES)


def test_higher_frames_are_kept_for_context() -> None:
    # Reading a scalp with no idea where H1 sits is how a trader sells into an
    # uptrend on a three-minute pullback.
    assert Timeframe.H1 in CONTEXT_TIMEFRAMES
    assert Timeframe.H4 in CONTEXT_TIMEFRAMES


def test_m30_and_d1_are_excluded_entirely() -> None:
    # M30 says nothing M15 and H1 do not; D1 cannot time a one-minute entry.
    assert not is_active_timeframe(Timeframe.M30)
    assert not is_active_timeframe(Timeframe.D1)


def test_active_set_is_decisions_plus_context() -> None:
    assert set(ACTIVE_TIMEFRAMES) == set(DECISION_TIMEFRAMES) | set(CONTEXT_TIMEFRAMES)
    assert len(ACTIVE_TIMEFRAMES) == len(set(ACTIVE_TIMEFRAMES))


def test_mtf_stack_runs_slowest_to_fastest() -> None:
    order = [Timeframe.H4, Timeframe.H1, Timeframe.M15]
    assert list(MTF_CONTEXT_STACK) == order
    assert MTF_CONTEXT_STACK_CODES == ("H4", "H1", "M15")


def test_mtf_stack_is_a_scalpers_ladder_not_a_swing_traders() -> None:
    # The stock stack was D1/H4/H1. M15 belongs in a scalper's context; D1 does
    # not belong anywhere in it.
    assert Timeframe.M15 in MTF_CONTEXT_STACK
    assert Timeframe.D1 not in MTF_CONTEXT_STACK


def test_mtf_stack_frames_are_all_fetched() -> None:
    """Context the platform never stores is context the agent cannot read."""
    for timeframe in MTF_CONTEXT_STACK:
        assert is_active_timeframe(timeframe)


def test_the_default_series_frame_is_a_scalp_frame() -> None:
    """A label for an unlabelled series, never a decision — but still a frame a
    scalp can legitimately live on, since a plan may end up tracked against it."""
    assert is_decision_timeframe(DEFAULT_SERIES_TIMEFRAME)


def test_analysis_bounds_are_ordered() -> None:
    assert MIN_CANDLES_FOR_ANALYSIS < ANALYSIS_WINDOW_BARS
    assert MIN_CANDLES_FOR_ANALYSIS >= 60


def test_string_codes_are_accepted() -> None:
    assert is_decision_timeframe("M5")
    assert not is_decision_timeframe("H4")

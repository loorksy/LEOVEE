"""Plan sanity: does the plan survive its own costs?

Not execution logic. Every check here is about whether the *recommendation* is
sound, which matters identically on a platform that never sends an order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.engines.plan_sanity import (
    GOLD_STATIC_SPREAD_PIPS,
    MIN_COST_MULTIPLE,
    SESSION_SPREAD_MULTIPLIER,
    estimate_spread_pips,
    reward_risk,
    risk_policy_for,
    round_trip_cost_pips,
    run_plan_sanity_engine,
    session_at,
)
from app.models.enums import Timeframe

pytestmark = pytest.mark.no_db

# London: the baseline session, multiplier 1.0, so cost arithmetic in these
# tests is readable without a session correction in every expectation.
LONDON = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)


def _plan(**overrides: Any) -> dict[str, Any]:
    base = {
        "entry": 2000.0,
        "stop": 1996.0,
        "targets": [2008.0],
        "atr": 5.0,
        "observed_spread_pips": 20.0,
        "moment": LONDON,
    }
    return {**base, **overrides}


def test_a_sound_scalp_plan_passes() -> None:
    result = run_plan_sanity_engine(**_plan())
    assert result["viable"] is True
    assert result["failures"] == []
    assert result["reward_risk"] == pytest.approx(2.0)


def test_a_stop_inside_the_spread_is_fatal() -> None:
    """The quote alone closes this trade before price has moved at all."""
    # Gold pip is 0.01, so a 20-pip spread is 0.20 in price. A 0.15 stop sits
    # inside it.
    result = run_plan_sanity_engine(**_plan(entry=2000.0, stop=1999.85, targets=[2008.0]))
    assert result["viable"] is False
    assert "STOP_INSIDE_SPREAD" in result["failures"]


def test_a_target_that_does_not_clear_the_round_trip_is_fatal() -> None:
    """Structurally losing, whatever its win rate.

    Spread and slippage are each paid twice. A first target inside three times
    that is not a slightly worse plan than a good one — the arithmetic never
    closes, and how often it wins does not enter into it.
    """
    result = run_plan_sanity_engine(**_plan(targets=[2000.5]))
    assert result["viable"] is False
    assert "TARGET_BELOW_COST_FLOOR" in result["failures"]
    assert result["required_target_pips"] == pytest.approx(
        round_trip_cost_pips(20.0) * MIN_COST_MULTIPLE
    )


def test_a_zero_distance_stop_is_unpriceable_not_merely_wide() -> None:
    result = run_plan_sanity_engine(**_plan(stop=2000.0))
    assert result["viable"] is False
    assert result["failures"] == ["STOP_DISTANCE_ZERO"]
    assert result["reward_risk"] is None


def test_a_missing_target_fails_rather_than_defaulting() -> None:
    result = run_plan_sanity_engine(**_plan(targets=[]))
    assert result["viable"] is False
    assert "NO_TARGET" in result["failures"]


def test_a_high_spread_relative_to_risk_warns_without_failing() -> None:
    """Expensive is not the same as impossible — the caller decides."""
    result = run_plan_sanity_engine(**_plan(atr=0.5, stop=1999.0, targets=[2020.0]))
    assert "SPREAD_HIGH_VS_RISK" in result["warnings"]
    assert result["viable"] is True


def test_reward_risk_below_one_warns_and_is_never_silent() -> None:
    result = run_plan_sanity_engine(**_plan(stop=1990.0, targets=[2005.0]))
    assert "REWARD_RISK_BELOW_ONE" in result["warnings"]


# --- the cost model ---------------------------------------------------------


def test_a_modelled_spread_is_labelled_as_modelled() -> None:
    """A fallback returned as a measurement is the failure this prevents."""
    estimate = estimate_spread_pips(observed_pips=None, moment=LONDON)
    assert estimate.source == "static_model"
    assert estimate.pips == pytest.approx(GOLD_STATIC_SPREAD_PIPS)

    result = run_plan_sanity_engine(**_plan(observed_spread_pips=None))
    assert "SPREAD_MODELLED_NOT_OBSERVED" in result["warnings"]


def test_an_observed_quote_is_labelled_as_observed() -> None:
    estimate = estimate_spread_pips(observed_pips=12.0, moment=LONDON)
    assert estimate.source == "observed"
    assert estimate.pips == pytest.approx(12.0)


@pytest.mark.parametrize(
    ("hour", "session"),
    [
        (2, "asia"),
        (9, "london"),
        (14, "london_new_york_overlap"),
        (18, "new_york"),
        (23, "asia"),
    ],
)
def test_sessions_are_read_off_the_utc_hour(hour: int, session: str) -> None:
    assert session_at(datetime(2026, 6, 10, hour, tzinfo=UTC)) == session


def test_asia_costs_more_than_the_overlap() -> None:
    """The ordering is what matters: thinnest book, widest spread.

    A plan that only works at overlap spreads should fail at Asian ones rather
    than pass on a number it will not be filled at.
    """
    assert SESSION_SPREAD_MULTIPLIER["asia"] > SESSION_SPREAD_MULTIPLIER["london"]
    assert (
        SESSION_SPREAD_MULTIPLIER["london"] > SESSION_SPREAD_MULTIPLIER["london_new_york_overlap"]
    )
    asia = estimate_spread_pips(observed_pips=10.0, moment=datetime(2026, 6, 10, 2, tzinfo=UTC))
    overlap = estimate_spread_pips(observed_pips=10.0, moment=datetime(2026, 6, 10, 14, tzinfo=UTC))
    assert asia.pips > overlap.pips


def test_round_trip_charges_both_sides() -> None:
    assert round_trip_cost_pips(spread_pips=10.0, slippage_pips=2.0) == pytest.approx(24.0)
    assert round_trip_cost_pips(spread_pips=-5.0, slippage_pips=-5.0) == 0.0


def test_reward_risk_is_computed_from_the_levels_not_asserted() -> None:
    assert reward_risk(2000.0, 1990.0, 2020.0) == pytest.approx(2.0)
    assert reward_risk(2000.0, 2000.0, 2020.0) is None
    assert reward_risk(2000.0, 1990.0, None) is None


# --- the per-frame policy ---------------------------------------------------


def test_faster_frames_get_tighter_stops_and_shorter_holds() -> None:
    """A scalp is not a slow trade in miniature."""
    fast = risk_policy_for(Timeframe.M1)
    slow = risk_policy_for(Timeframe.M15)
    assert fast.stop_atr_multiple < slow.stop_atr_multiple
    assert fast.maximum_holding_bars < slow.maximum_holding_bars
    assert fast.target_r[0] < fast.target_r[1]


def test_a_non_decision_frame_has_no_policy() -> None:
    """H1 is context. There is no plan geometry for a frame we never trade."""
    with pytest.raises(ValueError, match="not a decision timeframe"):
        risk_policy_for(Timeframe.H1)

"""Activation rules: what a conditional plan is actually waiting for.

The distinctions between the kinds are the substance. A touch, a close beyond, a
confirmed break, a retest and a rejection describe different things that "price
reached X" would flatten into one — and the difference between a wick through a
level and a close beyond it is the difference between a sweep and a break.
"""

from __future__ import annotations

import pytest

from app.engines.bar import OHLCBar
from app.services.recommendations.activation import (
    ActivationKind,
    BreakoutRule,
    CandleCloseRule,
    CompositeRule,
    PriceTouchRule,
    RejectionRule,
    RetestRule,
    RetestZone,
    evaluate_activation,
    explain_incoherence,
)
from app.tests.bars import bar

pytestmark = pytest.mark.no_db


def _series(*specs: tuple[float, float, float, float]) -> list[OHLCBar]:
    return [bar(open=o, high=h, low=lo, close=c) for o, h, lo, c in specs]


# --- price touch -------------------------------------------------------------


def test_a_touch_is_satisfied_by_a_wick() -> None:
    """A touch means price got there. It does not ask how convincingly."""
    bars = _series((2010, 2011, 2004.5, 2009))
    outcome = evaluate_activation(PriceTouchRule(level=2005.0), bars)
    assert outcome.satisfied
    assert outcome.at_index == 0


def test_a_touch_that_never_happened_stays_pending() -> None:
    bars = _series((2010, 2011, 2008, 2009))
    assert evaluate_activation(PriceTouchRule(level=2005.0), bars).pending


def test_a_directional_touch_only_counts_from_the_named_side() -> None:
    approaching_from_above = _series((2010, 2011, 2004.5, 2009))
    rule = PriceTouchRule(level=2005.0, direction="above")
    assert evaluate_activation(rule, approaching_from_above).satisfied


# --- closes beyond -----------------------------------------------------------


def test_a_wick_through_does_not_satisfy_a_close_rule() -> None:
    """The whole reason the two kinds exist separately.

    A wick beyond a level is a sweep — price reached for resting orders and was
    rejected — and a plan waiting for a *break* must not activate on it.
    """
    swept = _series((2000, 2010, 1999, 2001))
    rule = CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2005.0)
    assert evaluate_activation(rule, swept).pending

    broke = _series((2000, 2010, 1999, 2007))
    assert evaluate_activation(rule, broke).satisfied


def test_closes_must_be_consecutive_not_merely_numerous() -> None:
    """Three closes above with one below between them is a level being fought
    over, not confirmation of anything."""
    interrupted = _series(
        (2000, 2008, 1999, 2007),
        (2007, 2008, 1999, 2001),
        (2001, 2008, 1999, 2007),
    )
    rule = CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2005.0, closes=2)
    assert evaluate_activation(rule, interrupted).pending

    consecutive = _series(
        (2000, 2008, 1999, 2007),
        (2007, 2009, 2006, 2008),
    )
    assert evaluate_activation(rule, consecutive).satisfied


def test_tolerance_is_in_price_units_and_widens_the_bar() -> None:
    marginal = _series((2000, 2006, 1999, 2005.4))
    strict = CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2005.0, tolerance=0.5)
    assert evaluate_activation(strict, marginal).pending
    loose = CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2005.0, tolerance=0.1)
    assert evaluate_activation(loose, marginal).satisfied


# --- breakout, retest, rejection ---------------------------------------------


def test_a_breakout_carries_its_direction_so_a_mismatch_is_checkable() -> None:
    bars = _series((2000, 2010, 1999, 2007))
    assert evaluate_activation(BreakoutRule(level=2005.0, direction="above"), bars).satisfied
    assert evaluate_activation(BreakoutRule(level=2005.0, direction="below"), bars).pending


def test_a_retest_requires_the_three_phases_in_order() -> None:
    """A retest before the break is not a retest — it is the approach."""
    rule = RetestRule(
        level=2005.0, direction="above", retest_zone=RetestZone(low=2003.0, high=2006.0)
    )

    broke_only = _series((2000, 2010, 1999, 2008))
    assert evaluate_activation(rule, broke_only).pending

    broke_and_returned = _series(
        (2000, 2010, 1999, 2008),
        (2008, 2009, 2004, 2005),
    )
    assert evaluate_activation(rule, broke_and_returned).pending

    complete = _series(
        (2000, 2010, 1999, 2008),
        (2008, 2009, 2004, 2005),
        (2005, 2012, 2004, 2011),
    )
    outcome = evaluate_activation(rule, complete)
    assert outcome.satisfied
    assert outcome.at_index == 2


def test_a_rejection_needs_both_the_pierce_and_the_close_back() -> None:
    """A close beyond is a break, and a bar that never reached rejected nothing."""
    rule = RejectionRule(level=2000.0, direction="above")

    rejected = _series((2005, 2006, 1996, 2004))
    assert evaluate_activation(rule, rejected).satisfied

    broke_through = _series((2005, 2006, 1996, 1997))
    assert evaluate_activation(rule, broke_through).pending

    never_reached = _series((2005, 2006, 2003, 2004))
    assert evaluate_activation(rule, never_reached).pending


# --- composites --------------------------------------------------------------


def test_all_requires_every_leaf_and_dates_from_the_last() -> None:
    rule = CompositeRule(
        operator="all",
        rules=[
            PriceTouchRule(level=2005.0),
            CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2008.0),
        ],
    )
    partial = _series((2010, 2011, 2004, 2006))
    assert evaluate_activation(rule, partial).pending

    both = _series((2010, 2011, 2004, 2006), (2006, 2012, 2005, 2011))
    outcome = evaluate_activation(rule, both)
    assert outcome.satisfied
    assert outcome.at_index == 1


def test_any_is_satisfied_by_the_first_leaf_to_fire() -> None:
    rule = CompositeRule(
        operator="any",
        rules=[
            PriceTouchRule(level=1990.0),
            CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2005.0),
        ],
    )
    bars = _series((2000, 2010, 1999, 2007))
    assert evaluate_activation(rule, bars).satisfied


def test_composites_are_one_level_deep() -> None:
    """A boolean expression tree is not something a trader says out loud, and
    everything that reads a rule would have to handle arbitrary nesting."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CompositeRule(
            operator="all",
            rules=[
                PriceTouchRule(level=2005.0),
                CompositeRule(operator="any", rules=[PriceTouchRule(level=1.0)]),  # type: ignore[list-item]
            ],
        )


def test_a_composite_needs_at_least_two_rules() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CompositeRule(operator="all", rules=[PriceTouchRule(level=2005.0)])


# --- coherence ---------------------------------------------------------------


def test_a_condition_price_already_meets_is_not_a_condition() -> None:
    """It activates on the next bar whatever happens — an immediate plan wearing
    a condition, with a reader waiting for a trigger that already fired."""
    rule = CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2000.0)
    problem = explain_incoherence(rule, direction="BUY", current_price=2010.0)
    assert problem is not None
    assert "already" in problem


def test_a_long_cannot_wait_on_the_case_that_kills_it() -> None:
    rule = RejectionRule(level=2000.0, direction="below")
    problem = explain_incoherence(rule, direction="BUY", current_price=1999.0)
    assert problem is not None
    assert "invalidates" in problem


def test_a_coherent_condition_reports_no_problem() -> None:
    rule = CandleCloseRule(kind=ActivationKind.CANDLE_CLOSE_ABOVE, level=2010.0)
    assert explain_incoherence(rule, direction="BUY", current_price=2000.0) is None


def test_a_touch_is_never_reported_as_already_satisfied() -> None:
    """A touch is instantaneous by design: if price is there, the plan is live
    now, and that is exactly what a touch condition means."""
    rule = PriceTouchRule(level=2000.0)
    assert explain_incoherence(rule, direction="BUY", current_price=2000.0) is None


def test_no_bars_is_pending_rather_than_satisfied() -> None:
    assert evaluate_activation(PriceTouchRule(level=2000.0), []).pending

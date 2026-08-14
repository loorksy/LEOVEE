"""Tradability: the moment, not the analysis.

Conflating this with confidence is the mistake it exists to prevent. A plan can
be entirely convincing and untradeable — the entry is forty points away, the
session is closed, the spread has widened past what the stop absorbs. Publishing
that as "low confidence" tells the reader the analysis is weak when the analysis
is fine and the moment is wrong.
"""

from __future__ import annotations

import pytest

from app.services.recommendations.tradability import (
    NOW_ATR_DISTANCE,
    SOON_ATR_DISTANCE,
    Tradability,
    TradabilityAssessment,
    assess_tradability,
)

pytestmark = pytest.mark.no_db


def _at(distance_atr: float, **overrides: object) -> TradabilityAssessment:
    return assess_tradability(
        entry=2000.0,
        current_price=2000.0 + distance_atr * 2.0,
        atr=2.0,
        **overrides,  # type: ignore[arg-type]
    )


def test_price_at_the_entry_is_now() -> None:
    assert _at(0.0).tradability is Tradability.NOW


def test_an_entry_is_a_zone_not_a_tick() -> None:
    """Demanding an exact touch means every plan reads as `soon` forever."""
    assert _at(NOW_ATR_DISTANCE * 0.9).tradability is Tradability.NOW


def test_an_approaching_entry_is_soon() -> None:
    assessment = _at(1.0)
    assert assessment.tradability is Tradability.SOON
    assert assessment.distance_atr == pytest.approx(1.0)
    # A colour with no reason is not information.
    assert "ATR away" in assessment.reason


def test_a_distant_entry_is_watch_only() -> None:
    assert _at(SOON_ATR_DISTANCE + 1).tradability is Tradability.WATCH_ONLY


def test_an_unviable_plan_is_rejected_and_never_rendered() -> None:
    """Not a weak opportunity. Rendering it invites someone to take it."""
    assessment = _at(0.0, plan_viable=False, plan_failures=["TARGET_INSIDE_NOISE"])
    assert assessment.tradability is Tradability.REJECTED
    assert assessment.renderable is False
    assert assessment.blockers == ["TARGET_INSIDE_NOISE"]


def test_rejection_outranks_a_perfect_entry() -> None:
    """A plan whose arithmetic never closes is not an opportunity at any
    distance."""
    assert _at(0.0, plan_viable=False).tradability is Tradability.REJECTED


def test_a_closed_market_outranks_a_distant_entry() -> None:
    """ "The market is closed" is a complete explanation; "the entry is 40 points
    away" is not one when nothing can be entered anyway."""
    assessment = _at(10.0, market_open=False)
    assert assessment.reason == "market closed"
    assert assessment.blockers == ["MARKET_CLOSED"]


def test_an_unfired_condition_says_what_to_watch_for() -> None:
    """A pending condition is a reason to watch, not a defect."""
    assessment = _at(
        0.0, awaiting_activation=True, activation_detail="waiting on a close above 2005"
    )
    assert assessment.tradability is Tradability.WATCH_ONLY
    assert "2005" in assessment.reason
    assert assessment.blockers == ["AWAITING_ACTIVATION"]


def test_no_price_is_watch_only_rather_than_a_guess() -> None:
    assessment = assess_tradability(entry=2000.0, current_price=None, atr=2.0)
    assert assessment.tradability is Tradability.WATCH_ONLY
    assert assessment.blockers == ["NO_PRICE"]


def test_zero_volatility_cannot_be_measured_against() -> None:
    assessment = assess_tradability(entry=2000.0, current_price=2000.0, atr=0.0)
    assert assessment.tradability is Tradability.WATCH_ONLY


def test_the_assessment_serialises_for_the_card() -> None:
    payload = _at(1.0).to_dict()
    assert payload["tradability"] == "soon"
    assert payload["reason"]
    assert payload["distance_atr"] == pytest.approx(1.0)


def test_an_entry_far_enough_away_is_rejected_not_merely_watched() -> None:
    """Publishing a level price may never revisit inside the plan's own lifetime
    is noise, and the caller should re-plan near the market instead."""
    assessment = _at(6.0)
    assert assessment.tradability is Tradability.REJECTED
    assert assessment.renderable is False
    assert "re-plan" in assessment.reason


def test_inside_the_spread_counts_as_at_the_entry() -> None:
    """Waiting for a better price there costs more than the trade's own round
    trip, so it is at the entry in every sense that matters."""
    assessment = assess_tradability(entry=2000.0, current_price=2000.3, atr=2.0, spread=0.5)
    assert assessment.tradability is Tradability.NOW
    assert "spread" in assessment.reason

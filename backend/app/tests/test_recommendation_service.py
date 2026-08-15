"""recommendation_to_card: the exact shape the frontend's recommendation cards render.

A plain unit test, no DB — the function is a pure dict-builder over a
Recommendation instance.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.recommendation import Recommendation
from app.services.recommendation_service import recommendation_to_card

pytestmark = pytest.mark.no_db


def _recommendation(**overrides: object) -> Recommendation:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "symbol_id": uuid.uuid4(),
        "direction": RecommendationDirection.BUY,
        "status": RecommendationStatus.READY,
        "confidence_calibrated": None,
        "thesis_text": None,
        "entry": None,
        "stop": None,
        "targets_json": [],
        "evidence_json": {},
        "tradability": None,
        "tradability_reason": None,
    }
    defaults.update(overrides)
    return Recommendation(**defaults)


def test_the_card_carries_tradability_alongside_the_direction_it_qualifies() -> None:
    """Tradability is a separate axis from confidence/direction (ADR-adjacent
    rule): a convincing plan can still be untradeable, and the card must be
    able to say so without touching the direction or status it renders."""
    rec = _recommendation(tradability="soon", tradability_reason="entry is 40 pips away")

    card = recommendation_to_card(rec, symbol_code="XAUUSD")

    assert card["tradability"] == "soon"
    assert card["tradability_reason"] == "entry is 40 pips away"
    # Untouched by the new fields.
    assert card["direction"] == "BUY"
    assert card["status"] == "READY"


def test_a_recommendation_with_no_tradability_assessment_reports_none() -> None:
    """Not every recommendation has gone through the tradability check yet —
    the card must say so plainly rather than default to a value that reads as
    an assessment that was never made."""
    rec = _recommendation()

    card = recommendation_to_card(rec, symbol_code="XAUUSD")

    assert card["tradability"] is None
    assert card["tradability_reason"] is None

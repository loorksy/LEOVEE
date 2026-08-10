from __future__ import annotations

from decimal import Decimal

from app.engines.thesis_monitor import evaluate_thesis_monitor
from app.models.enums import RecommendationDirection, ThesisStatus


def test_structure_break_invalidates_bullish_thesis() -> None:
    result = evaluate_thesis_monitor(
        thesis_status=ThesisStatus.ACTIVE.value,
        direction=RecommendationDirection.BUY.value,
        last_price=Decimal("1.0900"),
        structure={"swing_low": 1.0950, "swing_high": 1.1200},
        invalidation={"swing_low": 1.0950},
    )
    assert result["action"] == "TRANSITION"
    assert result["new_status"] == ThesisStatus.INVALIDATED.value
    assert result["event_type"] == "THESIS_INVALIDATED"


def test_target_reached_on_buy() -> None:
    result = evaluate_thesis_monitor(
        thesis_status=ThesisStatus.ACTIVE.value,
        direction=RecommendationDirection.BUY.value,
        last_price=Decimal("1.1100"),
        structure={},
        invalidation={"target_price": 1.1050},
    )
    assert result["new_status"] == ThesisStatus.TARGET_REACHED.value

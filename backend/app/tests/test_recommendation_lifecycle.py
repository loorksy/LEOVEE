from __future__ import annotations

import pytest

from app.models.enums import RecommendationStatus
from app.services.recommendation_lifecycle import assert_recommendation_transition


def test_recommendation_valid_transition() -> None:
    assert_recommendation_transition(RecommendationStatus.READY, RecommendationStatus.ACTIVE)


def test_recommendation_invalid_transition_raises() -> None:
    with pytest.raises(ValueError, match="invalid_transition"):
        assert_recommendation_transition(RecommendationStatus.DETECTED, RecommendationStatus.ACTIVE)

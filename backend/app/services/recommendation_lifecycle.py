from __future__ import annotations

from app.models.enums import RecommendationStatus

TERMINAL_RECOMMENDATION_STATUSES = frozenset(
    {
        RecommendationStatus.TARGET_REACHED,
        RecommendationStatus.INVALIDATED,
        RecommendationStatus.EXPIRED,
    }
)

RECOMMENDATION_TRANSITIONS: dict[RecommendationStatus, frozenset[RecommendationStatus]] = {
    RecommendationStatus.DETECTED: frozenset(
        {
            RecommendationStatus.ANALYZING,
            RecommendationStatus.INVALIDATED,
            RecommendationStatus.EXPIRED,
        }
    ),
    RecommendationStatus.ANALYZING: frozenset(
        {
            RecommendationStatus.FORMING,
            RecommendationStatus.INVALIDATED,
            RecommendationStatus.EXPIRED,
        }
    ),
    RecommendationStatus.FORMING: frozenset(
        {
            RecommendationStatus.WAITING_CONFIRMATION,
            RecommendationStatus.READY,
            RecommendationStatus.INVALIDATED,
        }
    ),
    RecommendationStatus.WAITING_CONFIRMATION: frozenset(
        {RecommendationStatus.READY, RecommendationStatus.INVALIDATED, RecommendationStatus.EXPIRED}
    ),
    RecommendationStatus.READY: frozenset(
        {
            RecommendationStatus.ACTIVE,
            RecommendationStatus.INVALIDATED,
            RecommendationStatus.EXPIRED,
        }
    ),
    RecommendationStatus.ACTIVE: frozenset(
        {
            RecommendationStatus.STRENGTHENING,
            RecommendationStatus.WEAKENING,
            RecommendationStatus.TARGET_REACHED,
            RecommendationStatus.INVALIDATED,
            RecommendationStatus.EXPIRED,
        }
    ),
    RecommendationStatus.STRENGTHENING: frozenset(
        {
            RecommendationStatus.ACTIVE,
            RecommendationStatus.TARGET_REACHED,
            RecommendationStatus.WEAKENING,
            RecommendationStatus.INVALIDATED,
        }
    ),
    RecommendationStatus.WEAKENING: frozenset(
        {
            RecommendationStatus.ACTIVE,
            RecommendationStatus.INVALIDATED,
            RecommendationStatus.EXPIRED,
        }
    ),
    RecommendationStatus.TARGET_REACHED: frozenset(),
    RecommendationStatus.INVALIDATED: frozenset(),
    RecommendationStatus.EXPIRED: frozenset(),
}


def assert_recommendation_transition(
    current: RecommendationStatus,
    new_status: RecommendationStatus,
) -> None:
    if current == new_status:
        return
    allowed = RECOMMENDATION_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        raise ValueError(f"invalid_transition:{current.value}->{new_status.value}")

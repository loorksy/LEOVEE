"""Which status changes are legal, and why the outcome does not need a trade.

**A recommendation's outcome is measured against price, not against execution.**
Leovee never places an order (D4), so nothing moves a plan to ACTIVE on its own —
that status means *the user reported taking it*. If reaching a target required
passing through ACTIVE first, then a plan the user never reported could never be
recorded as having worked, and the learning loop would only ever see the trades
someone bothered to log.

That is a biased sample in the worst direction: people report the ones they
took, and they take the ones that looked good. So READY leads directly to both
terminal outcomes. The question "did this plan work" is about price, and price
answers it whether or not anyone was on it.

ACTIVE remains for a trade the user has told us about, and keeps its own path to
the same outcomes — the two routes describe different things and both are real.
"""

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
            # A plan can grow stale while still forming: the structure it was
            # built on stops existing and nothing ever triggers.
            RecommendationStatus.EXPIRED,
        }
    ),
    RecommendationStatus.WAITING_CONFIRMATION: frozenset(
        {
            RecommendationStatus.READY,
            RecommendationStatus.INVALIDATED,
            RecommendationStatus.EXPIRED,
            # A condition can be overtaken: price runs to the target without
            # ever printing the trigger. The plan was right and untaken, and
            # recording it as expired would lose that.
            RecommendationStatus.TARGET_REACHED,
        }
    ),
    RecommendationStatus.READY: frozenset(
        {
            # The user told us they took it.
            RecommendationStatus.ACTIVE,
            # …or nobody did, and price answered anyway. Both terminal outcomes
            # are reachable without an execution, or the learning loop only ever
            # sees the trades someone chose to report — the ones that looked
            # good, which is exactly the wrong sample.
            RecommendationStatus.TARGET_REACHED,
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

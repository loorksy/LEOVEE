"""Can this be traded now, soon, or only watched?

A separate axis from confidence, and conflating them is the mistake this
prevents. A plan can be entirely convincing and untradeable — the entry is forty
points away, the session is closed, or the stop sits inside movement these very
candles show price giving back. Publishing that as "low confidence" tells the
reader the analysis is weak when the analysis is fine and the *moment* is
wrong.

Four classes, and the boundaries between them are decisions rather than
gradations:

``now`` — price is at the entry and nothing blocks it.
``soon`` — the plan is sound and the entry is within reach; worth watching.
``watch_only`` — the structure is real but something concrete is in the way.
``rejected`` — never rendered as a card at all. Two ways to earn it: the plan
does not survive the tape it was written for, or the entry is so far away that
publishing it as any kind of plan is noise. Neither is a weak opportunity, and
showing either invites someone to take it.

The order of the checks is deliberate: a blocked market beats a distant entry,
because "the market is closed" is a complete explanation and "the entry is far"
is not one when nothing can be entered anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "Tradability",
    "TradabilityAssessment",
    "assess_tradability",
    "NOW_ATR_DISTANCE",
    "SOON_ATR_DISTANCE",
]


class Tradability(StrEnum):
    NOW = "now"
    SOON = "soon"
    WATCH_ONLY = "watch_only"
    #: Never rendered as a card.
    REJECTED = "rejected"


#: Distance from entry, in ATR. Inside this, price is *at* the entry — a scalp
#: entry is a zone, not a tick, and demanding an exact touch means every plan
#: reads as `soon` forever.
NOW_ATR_DISTANCE = 0.25
#: Beyond this the entry is not "approaching", it is somewhere else.
SOON_ATR_DISTANCE = 2.0
#: Past this, publishing it as any kind of plan is noise. The caller should
#: re-plan near the market rather than shipping a level price may not revisit
#: inside the plan's own lifetime.
REJECT_ATR_DISTANCE = 4.0


@dataclass(frozen=True, slots=True)
class TradabilityAssessment:
    tradability: Tradability
    #: Why, in one phrase. The card shows it: "soon" with no reason is a colour
    #: rather than information.
    reason: str
    distance_atr: float | None = None
    blockers: list[str] = field(default_factory=list)

    @property
    def renderable(self) -> bool:
        return self.tradability is not Tradability.REJECTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "tradability": self.tradability.value,
            "reason": self.reason,
            "distance_atr": self.distance_atr,
            "blockers": list(self.blockers),
        }


def assess_tradability(
    *,
    entry: float | None,
    current_price: float | None,
    atr: float,
    plan_viable: bool = True,
    plan_failures: list[str] | None = None,
    market_open: bool = True,
    awaiting_activation: bool = False,
    activation_detail: str | None = None,
    spread: float | None = None,
) -> TradabilityAssessment:
    """Classify the moment, not the analysis."""
    failures = list(plan_failures or [])

    # First, because a plan whose arithmetic never closes is not an opportunity
    # at any distance, and rendering it invites someone to take it.
    if not plan_viable:
        return TradabilityAssessment(
            Tradability.REJECTED,
            reason="the plan does not survive the tape it was written for",
            blockers=failures,
        )

    if not market_open:
        # Before distance: "the market is closed" is a complete explanation, and
        # "the entry is 40 points away" is not one when nothing can be entered.
        return TradabilityAssessment(
            Tradability.WATCH_ONLY, reason="market closed", blockers=["MARKET_CLOSED"]
        )

    if awaiting_activation:
        # A condition that has not fired is a *reason to watch*, not a defect,
        # and it says exactly what to watch for.
        return TradabilityAssessment(
            Tradability.WATCH_ONLY,
            reason=activation_detail or "waiting on the entry condition",
            blockers=["AWAITING_ACTIVATION"],
        )

    if entry is None or current_price is None or not atr > 0:
        return TradabilityAssessment(
            Tradability.WATCH_ONLY,
            reason="no live price to measure the entry against",
            blockers=["NO_PRICE"],
        )

    absolute = abs(current_price - entry)
    if spread is not None and spread > 0 and absolute <= spread:
        # An *observed* quote, never a modelled one (ADR 0010): when the gap to
        # the entry is narrower than the live bid-ask, price is at the entry in
        # every sense a reader can act on. Absent a quote this is simply skipped
        # rather than filled in from an assumption.
        return TradabilityAssessment(
            Tradability.NOW,
            reason="price is inside the spread of the entry",
            distance_atr=round(absolute / atr, 3),
        )

    distance = absolute / atr
    if distance <= NOW_ATR_DISTANCE:
        return TradabilityAssessment(
            Tradability.NOW, reason="price is at the entry", distance_atr=round(distance, 3)
        )
    if distance <= SOON_ATR_DISTANCE:
        return TradabilityAssessment(
            Tradability.SOON,
            reason=f"entry {distance:.1f} ATR away",
            distance_atr=round(distance, 3),
        )
    if distance <= REJECT_ATR_DISTANCE:
        return TradabilityAssessment(
            Tradability.WATCH_ONLY,
            reason=f"entry {distance:.1f} ATR away",
            distance_atr=round(distance, 3),
            blockers=["ENTRY_DISTANT"],
        )
    return TradabilityAssessment(
        Tradability.REJECTED,
        reason=f"entry {distance:.1f} ATR away — re-plan near the market",
        distance_atr=round(distance, 3),
        blockers=["ENTRY_TOO_FAR_TO_PUBLISH"],
    )

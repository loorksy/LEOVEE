"""How much the record actually backs this decision — including when it does not.

**There is no simulated history (D7).** Every number here comes from
recommendations that closed in this workspace, which makes the sample small,
slow to grow, and the only honest evidence available. It also means the answer
for a brand-new workspace is *none*, and saying so plainly is the single most
important thing this module does.

**It reports strength; it never decides.** A plan with no matching history goes
out exactly as it would with history — same direction, same levels, same
tradability. What changes is what the reader is told about the record behind it.
Withholding analysis until statistics exist is not caution: it is a platform
that says nothing for months and calls the silence rigour.

**Reason codes, not sentences.** The backend returns a code and the numbers; the
words are chosen in the interface, where the reader's language is known. A
service that returns Arabic prose has decided the locale on behalf of every
caller, including the ones that are not people.

**No cross-workspace fallback.** The reference implementation, finding no rows
for the current user, re-queried without an owner filter and labelled the result
"platform evidence". Under RLS that read is impossible, and it should be: one
workspace's outcomes are not evidence about another's, and a confidence built
from someone else's record is the most expensive kind of wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.learning import StrategyStat
from app.services.strategies.calibration import WinRateCalibration, calibrate_win_rate
from app.services.strategies.matching_keys import ANY, Classification, read_ladder
from app.services.strategies.thresholds import (
    MIN_OUTCOMES_FOR_SUPPORT,
    MODERATE_INTERVAL_WIDTH,
    STRONG_INTERVAL_WIDTH,
)

__all__ = ["SupportLevel", "SupportReason", "StatisticalSupport", "assess_support"]


class SupportLevel(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    #: Some record, not enough of it. Distinct from `none` because "three
    #: outcomes, all wins" and "no outcomes" are different things to be told.
    PROVISIONAL = "provisional"
    NONE = "none"


class SupportReason(StrEnum):
    """What the interface renders. One code per situation the reader can be in."""

    NO_HISTORY = "SUPPORT_NO_HISTORY"
    PROVISIONAL = "SUPPORT_PROVISIONAL"
    SUSPENDED = "SUPPORT_SUSPENDED"
    AGGREGATED = "SUPPORT_AGGREGATED"
    PRESENT = "SUPPORT_PRESENT"


@dataclass(frozen=True, slots=True)
class StatisticalSupport:
    level: SupportLevel
    reason: SupportReason
    outcomes: int
    wins: int
    calibration: WinRateCalibration | None
    #: Which dimensions were averaged over to find these numbers. Non-empty
    #: means they come from a wider bucket than the plan's own, and the reader
    #: is entitled to know which.
    aggregated_over: tuple[str, ...] = ()
    suspended: bool = False

    @property
    def has_support(self) -> bool:
        return self.level in (SupportLevel.STRONG, SupportLevel.MODERATE, SupportLevel.WEAK)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "reason": self.reason.value,
            "outcomes": self.outcomes,
            "wins": self.wins,
            "aggregated_over": list(self.aggregated_over),
            "suspended": self.suspended,
            "calibration": self.calibration.to_dict() if self.calibration else None,
        }


_NO_HISTORY = StatisticalSupport(
    level=SupportLevel.NONE,
    reason=SupportReason.NO_HISTORY,
    outcomes=0,
    wins=0,
    calibration=None,
)

_LADDER_DIMENSIONS = ("setup_type", "regime_bucket", "session_bucket", "volatility_bucket")


def _widened_dimensions(exact: Classification, used: Classification) -> tuple[str, ...]:
    return tuple(
        name
        for name in _LADDER_DIMENSIONS
        if getattr(used, name) == ANY and getattr(exact, name) != ANY
    )


async def _stats_for(session: AsyncSession, rung: Classification) -> list[StrategyStat]:
    """Rows matching one rung. `ANY` means "do not constrain this column"."""
    query = select(StrategyStat).where(StrategyStat.strategy_code == rung.strategy_code)
    for column, value in (
        (StrategyStat.setup_type, rung.setup_type),
        (StrategyStat.regime_bucket, rung.regime_bucket),
        (StrategyStat.session_bucket, rung.session_bucket),
        (StrategyStat.volatility_bucket, rung.volatility_bucket),
    ):
        if value != ANY:
            query = query.where(column == value)
    result = await session.execute(query)
    return list(result.scalars().all())


async def assess_support(
    session: AsyncSession,
    tenant: TenantContext,
    classification: Classification,
) -> StatisticalSupport:
    """The strongest honest statement the record supports for this bucket.

    Walks the read ladder from the exact bucket outward and stops at the first
    rung with any outcomes at all. Stopping at the first *sufficient* rung would
    be worse: it would silently prefer a large loose average over a small exact
    one, and that trade belongs to the reader, not to this function.
    """
    await bind_workspace_rls(session, tenant)

    for rung in read_ladder(classification):
        stats = await _stats_for(session, rung)
        outcomes = sum(stat.occurrences for stat in stats)
        if outcomes <= 0:
            continue

        wins = sum(stat.wins for stat in stats)
        suspended = any(stat.suspended for stat in stats)
        widened = _widened_dimensions(classification, rung)
        calibration = calibrate_win_rate(wins=wins, samples=outcomes)

        if outcomes < MIN_OUTCOMES_FOR_SUPPORT:
            # Real outcomes, too few to grade. The count travels with the label
            # so "three, all wins" is not presented as an absence of evidence.
            return StatisticalSupport(
                level=SupportLevel.PROVISIONAL,
                reason=SupportReason.PROVISIONAL,
                outcomes=outcomes,
                wins=wins,
                calibration=calibration,
                aggregated_over=widened,
                suspended=suspended,
            )

        if suspended:
            # A bucket whose edge decayed is not weak evidence for the plan, it
            # is evidence against relying on it. Its own reason rather than
            # folded into `weak`, which reads as merely thin.
            return StatisticalSupport(
                level=SupportLevel.WEAK,
                reason=SupportReason.SUSPENDED,
                outcomes=outcomes,
                wins=wins,
                calibration=calibration,
                aggregated_over=widened,
                suspended=True,
            )

        width = calibration.width
        if calibration.statistically_sufficient and width <= STRONG_INTERVAL_WIDTH:
            level = SupportLevel.STRONG
        elif width <= MODERATE_INTERVAL_WIDTH:
            level = SupportLevel.MODERATE
        else:
            level = SupportLevel.WEAK

        return StatisticalSupport(
            level=level,
            reason=SupportReason.AGGREGATED if widened else SupportReason.PRESENT,
            outcomes=outcomes,
            wins=wins,
            calibration=calibration,
            aggregated_over=widened,
            suspended=False,
        )

    return _NO_HISTORY

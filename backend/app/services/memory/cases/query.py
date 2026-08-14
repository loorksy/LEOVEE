"""When has it looked like this before, and what came next?

Three stages, and the split between them is the design:

1. **Recall.** A cheap SQL prefilter on the categorical slots plus a pgvector
   nearest-neighbour scan. This narrows thousands of cases to a working set and
   is allowed to be approximate.
2. **Rank.** Exact weighted L1 over the eight slots, in process. The vector index
   uses L2 and is *not* the metric — it is a way of not reading every row.
   Reporting the index's distance as the similarity would silently rank by a
   different question than the one the memory was built to answer.
3. **Aggregate.** Under the minimum-sample rule, so a thin set reports counts and
   withholds rates.

**Cases are shared market history; the reader's own record is not.** Nothing
here is workspace-scoped, deliberately — "gold has been in this structure 47
times" is objective. How a *workspace's* plans fared lives in `strategy_stats`
behind RLS, and the two must never be added together.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_case import MarketCase
from app.services.memory.cases.fingerprint import (
    CaseFingerprint,
    fingerprint_similarity,
    fingerprint_vector,
)
from app.services.memory.cases.outcome import (
    CaseResolution,
    ForwardOutcome,
    OutcomeStats,
    summarize_outcomes,
)

__all__ = [
    "MIN_SIMILARITY",
    "CANDIDATE_LIMIT",
    "RESULT_LIMIT",
    "SimilarCase",
    "SimilarCaseResult",
    "find_similar_cases",
]

#: Below this two moments are not the same setup. A memory that returns its
#: nearest neighbours regardless of distance always has an answer, and an answer
#: that is always available is not evidence.
MIN_SIMILARITY = 0.72

#: How many rows the approximate stage may hand to the exact one. Wide enough
#: that the true nearest neighbours are almost certainly inside it, small enough
#: that the exact pass stays cheap.
CANDIDATE_LIMIT = 400

#: How many ranked cases are reported back.
RESULT_LIMIT = 50


@dataclass(frozen=True, slots=True)
class SimilarCase:
    case_ts: Any
    similarity: float
    fingerprint: CaseFingerprint
    outcome: ForwardOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_ts": self.case_ts.isoformat() if hasattr(self.case_ts, "isoformat") else None,
            "similarity": self.similarity,
            "fingerprint": self.fingerprint.to_dict(),
            "outcome": self.outcome.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SimilarCaseResult:
    cases: list[SimilarCase]
    stats: OutcomeStats
    #: How many rows the exact pass actually scored. Reported so a caller can
    #: tell "nothing was similar enough" from "nothing was looked at".
    candidates_considered: int
    direction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "candidates_considered": self.candidates_considered,
            "stats": self.stats.to_dict(),
            "cases": [case.to_dict() for case in self.cases[:10]],
        }


def _fingerprint_of(row: MarketCase) -> CaseFingerprint:
    return CaseFingerprint(
        regime=row.regime,  # type: ignore[arg-type]
        trend=row.trend,  # type: ignore[arg-type]
        range_zone=row.range_zone,  # type: ignore[arg-type]
        pullback_depth=row.pullback_depth,
        impulse_atr=row.impulse_atr,
        volatility=row.volatility,
        session=row.session,  # type: ignore[arg-type]
        structure_run=row.structure_run,
    )


def _outcome_of(row: MarketCase, direction: str) -> ForwardOutcome | None:
    if direction == "buy":
        resolution, bars, net_r = row.buy_resolution, row.buy_bars, row.buy_net_r
        mfe, mae = row.buy_mfe_atr, row.buy_mae_atr
    else:
        resolution, bars, net_r = row.sell_resolution, row.sell_bars, row.sell_net_r
        mfe, mae = row.sell_mfe_atr, row.sell_mae_atr
    if resolution is None or bars is None:
        return None
    return ForwardOutcome(
        resolution=CaseResolution(resolution),
        bars=bars,
        max_favourable_atr=mfe or 0.0,
        max_adverse_atr=mae or 0.0,
        net_r=net_r or 0.0,
    )


async def find_similar_cases(
    session: AsyncSession,
    *,
    symbol_id: uuid.UUID,
    timeframe: str,
    fingerprint: CaseFingerprint,
    direction: str,
    min_similarity: float = MIN_SIMILARITY,
    limit: int = RESULT_LIMIT,
    exclude_from: Any = None,
) -> SimilarCaseResult:
    """Past moments that resemble this one, and how they resolved.

    `exclude_from` drops cases at or after a timestamp. A backtest-free platform
    still has one way to fool itself here: retrieving cases from *after* the
    moment being analysed. That cannot happen live, but it can in a replay, and
    the guard costs one predicate.
    """
    probe = fingerprint_vector(fingerprint)

    query = select(MarketCase).where(
        MarketCase.symbol_id == symbol_id,
        MarketCase.timeframe == timeframe,
        # Direction of the structure is the one categorical the metric weights
        # most heavily; filtering on it up front keeps the candidate pool full
        # of plausible matches instead of spending it on opposites.
        MarketCase.trend == fingerprint.trend,
    )
    if exclude_from is not None:
        query = query.where(MarketCase.case_ts < exclude_from)
    query = query.order_by(MarketCase.embedding.l2_distance(probe)).limit(CANDIDATE_LIMIT)

    candidates = list((await session.execute(query)).scalars().all())

    scored: list[SimilarCase] = []
    for row in candidates:
        outcome = _outcome_of(row, direction)
        if outcome is None:
            continue
        stored = _fingerprint_of(row)
        similarity = fingerprint_similarity(fingerprint, stored)
        if similarity < min_similarity:
            continue
        scored.append(
            SimilarCase(
                case_ts=row.case_ts,
                similarity=similarity,
                fingerprint=stored,
                outcome=outcome,
            )
        )

    # Sorted on the exact metric, not on the index's distance. Ties break on the
    # older case, so the same query returns the same list rather than whatever
    # order the scan produced.
    scored.sort(key=lambda case: (-case.similarity, case.case_ts))
    top = scored[:limit]

    return SimilarCaseResult(
        cases=top,
        stats=summarize_outcomes([case.outcome for case in top]),
        candidates_considered=len(candidates),
        direction=direction,
    )

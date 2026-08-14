"""Turning a stretch of candles into remembered cases.

Sweeping a window produces one case per bar that has both enough history behind
it to be fingerprinted and enough future ahead of it to have resolved. The two
halves come from disjoint slices — that separation is what stops the memory from
predicting the past, and it is enforced by slicing here rather than trusted to a
caller.

**Idempotent by moment.** Re-sweeping an overlapping window updates rather than
duplicates. Without that, a nightly job that re-reads the last week silently
multiplies the weight of that week every time it runs, and the memory drifts
toward whatever was most recently re-indexed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.bar import OHLCBar
from app.models.market_case import MarketCase
from app.services.memory.cases.fingerprint import (
    MIN_CANDLES,
    CaseFingerprint,
    fingerprint_at,
    fingerprint_vector,
)
from app.services.memory.cases.outcome import (
    DEFAULT_HORIZON,
    ForwardOutcome,
    resolve_forward_outcome,
)

__all__ = ["IndexedCase", "build_cases", "store_cases"]


@dataclass(frozen=True, slots=True)
class IndexedCase:
    case_ts: object
    fingerprint: CaseFingerprint
    atr: float
    entry: float
    buy: ForwardOutcome
    sell: ForwardOutcome


def _atr_for(bars: Sequence[OHLCBar]) -> float:
    from app.services.memory.cases.fingerprint import _atr_of

    return _atr_of(list(bars))


def build_cases(
    bars: Sequence[OHLCBar],
    *,
    horizon: int = DEFAULT_HORIZON,
    stride: int = 1,
) -> list[IndexedCase]:
    """Fingerprint every qualifying moment and resolve it in both directions.

    Both directions, always: a moment is not bullish or bearish in itself, and
    only indexing the side the market happened to take would build a memory that
    always agrees with what came next.

    A case is emitted only when the full horizon of future bars exists. Indexing
    a moment with twelve bars ahead of it would record `unresolved` as though the
    market had declined to answer, when in fact the question was cut short — and
    those truncated rows would concentrate at the recent end, exactly where the
    memory is consulted most.
    """
    cases: list[IndexedCase] = []
    last_index = len(bars) - horizon
    for index in range(MIN_CANDLES, last_index, stride):
        history = list(bars[:index])
        fingerprint = fingerprint_at(history)
        if fingerprint is None:
            continue
        atr = _atr_for(history)
        if atr <= 0:
            continue
        moment = history[-1]
        future = list(bars[index : index + horizon])
        cases.append(
            IndexedCase(
                case_ts=moment.ts,
                fingerprint=fingerprint,
                atr=atr,
                entry=moment.close,
                buy=resolve_forward_outcome(
                    direction="buy", entry=moment.close, atr=atr, future=future, horizon=horizon
                ),
                sell=resolve_forward_outcome(
                    direction="sell", entry=moment.close, atr=atr, future=future, horizon=horizon
                ),
            )
        )
    return cases


async def store_cases(
    session: AsyncSession,
    cases: Sequence[IndexedCase],
    *,
    symbol_id: uuid.UUID,
    timeframe: str,
) -> int:
    """Persist cases, updating any moment already indexed. Returns rows written."""
    if not cases:
        return 0

    rows = [
        {
            "id": uuid.uuid4(),
            "symbol_id": symbol_id,
            "timeframe": timeframe,
            "case_ts": case.case_ts,
            "regime": case.fingerprint.regime,
            "trend": case.fingerprint.trend,
            "range_zone": case.fingerprint.range_zone,
            "pullback_depth": case.fingerprint.pullback_depth,
            "impulse_atr": case.fingerprint.impulse_atr,
            "volatility": case.fingerprint.volatility,
            "session": case.fingerprint.session,
            "structure_run": case.fingerprint.structure_run,
            "atr": case.atr,
            "entry": case.entry,
            "buy_resolution": case.buy.resolution.value,
            "buy_bars": case.buy.bars,
            "buy_net_r": case.buy.net_r,
            "buy_mfe_atr": case.buy.max_favourable_atr,
            "buy_mae_atr": case.buy.max_adverse_atr,
            "sell_resolution": case.sell.resolution.value,
            "sell_bars": case.sell.bars,
            "sell_net_r": case.sell.net_r,
            "sell_mfe_atr": case.sell.max_favourable_atr,
            "sell_mae_atr": case.sell.max_adverse_atr,
            "embedding": fingerprint_vector(case.fingerprint),
        }
        for case in cases
    ]

    statement = pg_insert(MarketCase).values(rows)
    # Update, not ignore: a re-sweep with a longer horizon or a corrected
    # fingerprint should replace what it supersedes. Ignoring would freeze the
    # first version of every case and make a fix un-deployable.
    updatable = {
        column: statement.excluded[column]
        for column in rows[0]
        if column not in ("id", "symbol_id", "timeframe", "case_ts")
    }
    await session.execute(
        statement.on_conflict_do_update(constraint="uq_market_case_moment", set_=updatable)
    )
    await session.flush()
    return len(rows)

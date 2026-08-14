"""Load the market and memory state that was visible at a historical moment.

Lives under ``app/services/`` and not ``app/engines/`` deliberately, and it was
under ``engines`` by mistake until the purity guard found it. It takes a
database session and a tenant context and loads rows; the engine layer is pure
functions of bars. The name says "engine" because that is what it is called in
the spec, not because of where it belongs.

Kept under D7 as a **visual review** tool: replaying a past analysis to look at
it again. It is not the statistical-validation surface D7 removed, and it makes
no claim about how a strategy would have performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.services import market_data, replay_memory


@dataclass(frozen=True, slots=True)
class ReplaySlice:
    symbol: str
    timeframe: Timeframe
    as_of: datetime


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def filter_candles_for_replay(candles: list[Candle], as_of: datetime) -> list[Candle]:
    """§101: hide candles strictly after replay time T."""
    cutoff = ensure_utc(as_of)
    return [c for c in candles if ensure_utc(c.ts) <= cutoff]


class HistoricalReplayEngine:
    """Loads market + memory state visible at historical time T only."""

    async def build_preview(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        replay_slice: ReplaySlice,
        *,
        candle_limit: int = 200,
    ) -> dict[str, Any]:
        symbol_row = await market_data.get_or_create_symbol(session, replay_slice.symbol)
        candles = await market_data.load_recent_candles(
            session,
            symbol_row.id,
            timeframe=replay_slice.timeframe,
            count=candle_limit,
        )
        visible = filter_candles_for_replay(candles, replay_slice.as_of)
        recall = await replay_memory.recall_at_time(
            session,
            tenant,
            symbol=replay_slice.symbol,
            as_of=replay_slice.as_of,
        )
        return {
            "schema_version": 1,
            "symbol": replay_slice.symbol.upper(),
            "timeframe": replay_slice.timeframe.value,
            "as_of": ensure_utc(replay_slice.as_of).isoformat(),
            "candles": [market_data.candle_to_dict(c) for c in visible],
            "candle_count": len(visible),
            "excluded_future_candles": len(candles) - len(visible),
            "recall": recall,
        }

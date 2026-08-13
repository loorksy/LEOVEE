"""Load the context ladder and read it.

The multi-timeframe engine measures bias from bars, so this is what puts the
bars in front of it: one fetch per frame in the stack, plus the frame the
decision will be made on.

The window is the full analysis window rather than a token 80 candles. The
regime classifier needs sixty bars before it will say anything at all, and its
baselines are medians over the sixty *before* the current one — hand it eighty
and every baseline is computed from a window that barely exists, which is how a
normal session reads as a volatility expansion.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeframes import ANALYSIS_WINDOW_BARS, INTERIM_DECISION_TIMEFRAME
from app.engines.bar import OHLCBar, bars_from_candles
from app.engines.market_intelligence import run_market_intelligence_engine
from app.engines.mtf import default_mtf_stack, run_mtf_engine
from app.models.enums import Timeframe
from app.providers.market.base import MarketDataProvider
from app.services import market_data

__all__ = ["build_mtf_intelligence"]


async def build_mtf_intelligence(
    session: AsyncSession,
    *,
    symbol: str,
    provider: MarketDataProvider | None = None,
    stack: tuple[str, ...] | None = None,
    decision_timeframe: Timeframe = INTERIM_DECISION_TIMEFRAME,
) -> dict[str, Any]:
    timeframes = stack or default_mtf_stack()
    wanted = list(dict.fromkeys([*timeframes, decision_timeframe.value]))

    bars_by_timeframe: dict[str, list[OHLCBar]] = {}
    intelligence_by_tf: dict[str, dict[str, Any]] = {}
    for tf_value in wanted:
        _, candles = await market_data.fetch_and_store_candles(
            session,
            symbol_code=symbol,
            timeframe=Timeframe(tf_value),
            count=ANALYSIS_WINDOW_BARS,
            provider=provider,
        )
        bars = bars_from_candles(candles)
        bars_by_timeframe[tf_value] = bars
        intelligence_by_tf[tf_value] = run_market_intelligence_engine(bars)

    mtf = run_mtf_engine(
        bars_by_timeframe,
        decision_timeframe=decision_timeframe.value,
        stack=timeframes,
    )
    return {"intelligence_by_tf": intelligence_by_tf, "mtf": mtf}

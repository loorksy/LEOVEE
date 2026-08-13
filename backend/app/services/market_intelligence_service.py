from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.bar import OHLCBar, bars_from_candles
from app.engines.market_intelligence import run_market_intelligence_engine
from app.engines.mtf import default_mtf_stack, run_mtf_engine
from app.models.enums import Timeframe
from app.providers.market.base import MarketDataProvider
from app.services import market_data


async def build_mtf_intelligence(
    session: AsyncSession,
    *,
    symbol: str,
    provider: MarketDataProvider | None = None,
    stack: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Load candles per timeframe and compute intelligence + MTF alignment."""
    timeframes = stack or default_mtf_stack()
    intelligence_by_tf: dict[str, dict[str, Any]] = {}
    for tf_value in timeframes:
        tf = Timeframe(tf_value)
        _, candles = await market_data.fetch_and_store_candles(
            session,
            symbol_code=symbol,
            timeframe=tf,
            count=80,
            provider=provider,
        )
        bars: list[OHLCBar] = bars_from_candles(candles)
        intelligence_by_tf[tf_value] = run_market_intelligence_engine(bars)
    mtf = run_mtf_engine(intelligence_by_tf, stack=timeframes)
    return {"intelligence_by_tf": intelligence_by_tf, "mtf": mtf}

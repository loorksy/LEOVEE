from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.liquidity import run_liquidity_engine
from app.engines.structure import run_structure_engine
from app.engines.volatility import OHLCBar, run_volatility_engine
from app.engines.zones import run_zones_engine
from app.models.market_artifacts import MarketEvent, PriceZone, Structure
from app.services import market_data
from app.services.market.engine_persistence import persist_engine_outputs


def _bars(n: int = 30) -> list[OHLCBar]:
    bars: list[OHLCBar] = []
    price = Decimal("1.1000")
    for i in range(n):
        o = price + Decimal(i) * Decimal("0.0001")
        bars.append(
            OHLCBar(
                open=o,
                high=o + Decimal("0.0005"),
                low=o - Decimal("0.0003"),
                close=o + Decimal("0.0002"),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_persist_engine_outputs_writes_artifacts(db_session: AsyncSession) -> None:
    symbol = await market_data.get_or_create_symbol(db_session, "EURUSD")
    bars = _bars()
    engines = {
        "structure": run_structure_engine(bars),
        "volatility": run_volatility_engine(bars),
        "liquidity": run_liquidity_engine(bars),
        "zones": run_zones_engine(bars),
    }
    counts = await persist_engine_outputs(
        db_session,
        symbol_id=symbol.id,
        timeframe="H1",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        engines=engines,
    )
    assert counts["structures"] >= 1
    assert counts["price_zones"] >= 2
    assert counts["market_events"] >= 1

    structures = await db_session.scalar(select(func.count()).select_from(Structure))
    zones = await db_session.scalar(select(func.count()).select_from(PriceZone))
    events = await db_session.scalar(select(func.count()).select_from(MarketEvent))
    assert structures and structures >= 1
    assert zones and zones >= 2
    assert events and events >= 1

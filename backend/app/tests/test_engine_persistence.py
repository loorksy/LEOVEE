from __future__ import annotations

from datetime import UTC, datetime

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
from app.tests.bars import rising_bars


def _bars(n: int = 30) -> list[OHLCBar]:
    return rising_bars(n)


@pytest.mark.asyncio
async def test_persist_engine_outputs_writes_artifacts(db_session: AsyncSession) -> None:
    """Persistence itself, driven by engine-shaped payloads.

    The real engines are placeholders until M4 (app/engines/status.py), so this
    supplies the payload shapes they will produce rather than calling them —
    otherwise the persistence logic would sit untested until the port lands.
    """
    symbol = await market_data.get_or_create_symbol(db_session, "EURUSD")
    engines = {
        "structure": {"bias": "BULLISH", "swing_high": 1.1050, "swing_low": 1.0980},
        "volatility": run_volatility_engine(_bars()),
        "liquidity": {"sweeps": ["BUY_SIDE"], "equal_highs": True, "equal_lows": False},
        "zones": {
            "zones": [
                {"type": "DEMAND", "low": 1.0980, "high": 1.1000, "strength": 0.7},
                {"type": "SUPPLY", "low": 1.1050, "high": 1.1070, "strength": 0.6},
            ]
        },
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


@pytest.mark.asyncio
async def test_unavailable_engines_persist_nothing(db_session: AsyncSession) -> None:
    """A declined answer must not become a stored artifact.

    Reading `bias` off an "unavailable" payload with a NEUTRAL default would
    write a structure row that later retrieval could not distinguish from a
    measured one.
    """
    symbol = await market_data.get_or_create_symbol(db_session, "EURUSD")
    bars = _bars()
    engines = {
        "structure": run_structure_engine(bars),
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
    assert counts == {"market_events": 0, "structures": 0, "price_zones": 0}
    assert await db_session.scalar(select(func.count()).select_from(Structure)) == 0
    assert await db_session.scalar(select(func.count()).select_from(PriceZone)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MarketEvent)) == 0

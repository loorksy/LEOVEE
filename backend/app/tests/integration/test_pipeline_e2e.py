from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import Timeframe
from app.models.market_artifacts import MarketEvent
from app.models.memory import AgentMemory
from app.models.recommendation import Thesis
from app.providers.market.base import NormalizedCandle
from app.services.analysis_service import run_analysis
from app.services.memory_service import retrieve_memories_for_symbol
from app.services.recommendation_service import get_recommendation
from app.tests.conftest import seed_user_org
from app.tests.doubles.market import FakeMarketDataProvider


def _synthetic_h1_series(count: int = 40) -> list[NormalizedCandle]:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[NormalizedCandle] = []
    price = Decimal("1.1000")
    for i in range(count):
        ts = start + timedelta(hours=i)
        o = price + Decimal(i) * Decimal("0.0002")
        candles.append(
            NormalizedCandle(
                symbol="EURUSD",
                timeframe=Timeframe.H1,
                ts=ts,
                open=o,
                high=o + Decimal("0.0010"),
                low=o - Decimal("0.0008"),
                close=o + Decimal("0.0005"),
                volume=Decimal("0"),
                complete=True,
                source="test_double",
            )
        )
    return candles


@pytest.mark.asyncio
async def test_pipeline_market_to_thesis(db_session: AsyncSession) -> None:
    user, _org, _membership = await seed_user_org(db_session)
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)

    provider = FakeMarketDataProvider(_synthetic_h1_series())
    result = await run_analysis(
        db_session,
        ctx,
        symbol="EURUSD",
        timeframe=Timeframe.H1,
        market_provider=provider,
        complete_pipeline=True,
    )
    await db_session.commit()

    assert result["recommendation_id"]
    assert result["thesis_id"]
    assert result["memory_id"]
    assert result["reasoning"]["approved"] is True

    rec = await get_recommendation(db_session, ctx, uuid.UUID(result["recommendation_id"]))
    await bind_workspace_rls(db_session, ctx)
    thesis = await db_session.scalar(
        select(Thesis).where(Thesis.id == uuid.UUID(result["thesis_id"]))
    )
    assert rec is not None
    assert thesis is not None
    assert thesis.recommendation_id == rec.id

    memory = await db_session.scalar(
        select(AgentMemory).where(AgentMemory.id == uuid.UUID(result["memory_id"]))
    )
    assert memory is not None
    assert memory.key.startswith("symbol:EURUSD:analysis:")

    recalled = await retrieve_memories_for_symbol(
        db_session,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        symbol="EURUSD",
    )
    assert any(item["id"] == result["memory_id"] for item in recalled)

    events = await db_session.execute(select(MarketEvent))
    assert len(events.scalars().all()) >= 1

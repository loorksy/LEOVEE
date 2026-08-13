from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.replay.historical_replay_engine import filter_candles_for_replay
from app.models.candle import Candle
from app.models.enums import Timeframe


def test_filter_candles_for_replay_excludes_future() -> None:
    t0 = datetime(2024, 1, 1, 10, tzinfo=UTC)
    t1 = datetime(2024, 1, 1, 12, tzinfo=UTC)
    as_of = datetime(2024, 1, 1, 11, tzinfo=UTC)
    symbol_id = __import__("uuid").uuid4()
    candles = [
        Candle(
            symbol_id=symbol_id,
            timeframe=Timeframe.H1,
            ts=t0,
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
        ),
        Candle(
            symbol_id=symbol_id,
            timeframe=Timeframe.H1,
            ts=t1,
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
        ),
    ]
    visible = filter_candles_for_replay(candles, as_of)
    assert len(visible) == 1
    assert visible[0].ts == t0


@pytest.mark.asyncio
async def test_recall_at_time_excludes_future_memories(
    db_session: AsyncSession,
) -> None:
    from app.core.tenant import resolve_tenant_context
    from app.models.memory import MemoryType
    from app.services import replay_memory
    from app.services.memory_service import store_memory
    from app.tests.conftest import seed_user_org

    user, org, _ = await seed_user_org(
        db_session,
        email="replay-mem@example.com",
        slug="replay-mem",
    )
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None

    past = await store_memory(
        db_session,
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        key="symbol:XAUUSD",
        content={"note": "past"},
        memory_type=MemoryType.SEMANTIC,
    )
    future = await store_memory(
        db_session,
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        key="symbol:XAUUSD",
        content={"note": "future"},
        memory_type=MemoryType.SEMANTIC,
    )
    await db_session.flush()
    future.created_at = datetime(2030, 1, 1, tzinfo=UTC)
    past.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    await db_session.commit()

    as_of = datetime(2025, 6, 1, tzinfo=UTC)
    recall = await replay_memory.recall_at_time(
        db_session,
        ctx,
        symbol="XAUUSD",
        as_of=as_of,
    )
    keys = {m["content"]["note"] for m in recall["memories"]}
    assert keys == {"past"}


@pytest.mark.asyncio
async def test_historical_replay_engine_preview_excludes_future_candles(
    db_session: AsyncSession,
) -> None:
    from app.core.tenant import resolve_tenant_context
    from app.engines.replay.historical_replay_engine import HistoricalReplayEngine, ReplaySlice
    from app.services import market_data
    from app.tests.conftest import seed_user_org

    user, org, _ = await seed_user_org(db_session, email="replay-c@example.com", slug="replay-c")
    ctx = await resolve_tenant_context(db_session, user.id)
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    early = datetime(2024, 1, 1, 8, tzinfo=UTC)
    late = datetime(2024, 1, 1, 16, tzinfo=UTC)
    for ts in (early, late):
        db_session.add(
            Candle(
                symbol_id=symbol.id,
                timeframe=Timeframe.H1,
                ts=ts,
                open=Decimal("1.1"),
                high=Decimal("1.2"),
                low=Decimal("1.0"),
                close=Decimal("1.15"),
            )
        )
    await db_session.commit()

    engine = HistoricalReplayEngine()
    as_of_slice = datetime(2024, 1, 1, 12, tzinfo=UTC)
    replay_slice = ReplaySlice(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        as_of=as_of_slice,
    )
    preview = await engine.build_preview(db_session, ctx, replay_slice)
    assert preview["candle_count"] == 1
    assert preview["excluded_future_candles"] >= 1
    assert all(c["ts"] <= preview["as_of"] for c in preview["candles"])

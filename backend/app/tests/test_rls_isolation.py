"""RLS isolation across tenant-owned tables (PostgreSQL only)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.infrastructure.rls import set_rls_session_context
from app.models.chart_annotation import ChartAnnotation, ChartAnnotationStatus
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.learning import StrategyStat, SymbolProfile
from app.models.memory import AgentMemory, Lesson, MemoryType
from app.models.oanda_connection import OandaConnection
from app.models.recommendation import Recommendation
from app.services import market_data, recommendation_service
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_rls_blocks_cross_workspace_reads(db_session: AsyncSession) -> None:
    user_a, org_a, _ = await seed_user_org(db_session, email="rls-a@example.com", slug="rls-a")
    user_b, org_b, _ = await seed_user_org(db_session, email="rls-b@example.com", slug="rls-b")

    ctx_a = await resolve_tenant_context(db_session, user_a.id)
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    assert ctx_a.workspace_id is not None
    assert ctx_b.workspace_id is not None

    symbol = await market_data.get_or_create_symbol(db_session, "EURUSD")
    rec_b = Recommendation(
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        symbol_id=symbol.id,
        direction=RecommendationDirection.BUY,
        status=RecommendationStatus.READY,
        confidence_calibrated=Decimal("0.6"),
    )
    db_session.add(rec_b)
    lesson_b = Lesson(
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        statement="Workspace B lesson",
        conditions_json={},
    )
    memory_b = AgentMemory(
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        memory_type=MemoryType.SEMANTIC,
        key="symbol:EURUSD",
        content_json={"note": "secret"},
    )
    stat_b = StrategyStat(
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        strategy_code="DEFAULT",
        setup_type="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        volatility_bucket="ANY",
        metadata_json={},
    )
    profile_b = SymbolProfile(
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        symbol_id=symbol.id,
        profile_json={"outcomes": []},
    )
    annotation_b = ChartAnnotation(
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        semantic_type="zone",
        geometry_json={"points": []},
        style_json={},
        status=ChartAnnotationStatus.ACTIVE,
    )
    oanda_b = OandaConnection(
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        account_id="101-001-1",
    )
    db_session.add_all([lesson_b, memory_b, stat_b, profile_b, annotation_b, oanda_b])
    await db_session.flush()

    await db_session.execute(text("SET ROLE leovee_app"))
    await set_rls_session_context(
        db_session,
        tenant_id=org_a.id,
        workspace_id=ctx_a.workspace_id,
        user_id=user_a.id,
    )

    async def count(model: type[Any]) -> int:
        result = await db_session.execute(select(model))
        return len(result.scalars().all())

    assert await count(Recommendation) == 0
    assert await count(Lesson) == 0
    assert await count(AgentMemory) == 0
    assert await count(StrategyStat) == 0
    assert await count(SymbolProfile) == 0
    assert await count(ChartAnnotation) == 0
    assert await count(OandaConnection) == 0

    # Workspace A can see only its own recommendation created under RLS context
    rec_a = await recommendation_service.create_recommendation(
        db_session,
        ctx_a,
        symbol_code="EURUSD",
        direction=RecommendationDirection.SELL,
    )
    await db_session.flush()
    visible = await db_session.scalar(select(Recommendation).where(Recommendation.id == rec_a.id))
    assert visible is not None
    assert visible.id == rec_a.id

    await set_rls_session_context(
        db_session,
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
    )
    foreign = await db_session.scalar(select(Recommendation).where(Recommendation.id == rec_a.id))
    assert foreign is None
    await db_session.execute(text("RESET ROLE"))


@pytest.mark.asyncio
async def test_rls_policies_are_forced(db_session: AsyncSession) -> None:
    row = await db_session.execute(
        text(
            """
            SELECT c.relname, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'recommendations'
            """
        )
    )
    relname, forced = row.one()
    assert relname == "recommendations"
    assert forced is True

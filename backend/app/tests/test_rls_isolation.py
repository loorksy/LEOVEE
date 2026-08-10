"""Runtime RLS enforcement and leovee_app role guarantees."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.tenant import resolve_tenant_context
from app.infrastructure.database import verify_runtime_db_role
from app.infrastructure.rls import clear_rls_session_context, set_rls_session_context
from app.main import app
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.learning import StrategyStat
from app.models.memory import AgentMemory, Lesson, MemoryType
from app.models.oanda_connection import OandaConnection
from app.models.recommendation import Recommendation
from app.services import market_data
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_leovee_app_role_is_not_superuser(db_session: AsyncSession) -> None:
    await verify_runtime_db_role(db_session)
    row = await db_session.execute(
        text(
            """
            SELECT rolsuper, rolbypassrls
            FROM pg_roles
            WHERE rolname = 'leovee_app'
            """
        )
    )
    rolsuper, rolbypassrls = row.one()
    assert rolsuper is False
    assert rolbypassrls is False


@pytest.mark.asyncio
async def test_rls_without_workspace_guc_returns_zero_rows(
    db_session: AsyncSession,
    privileged_session: AsyncSession,
) -> None:
    user, org, _ = await seed_user_org(privileged_session, email="noguc@example.com", slug="noguc")
    await privileged_session.commit()
    ctx = await resolve_tenant_context(privileged_session, user.id)
    assert ctx.workspace_id is not None
    symbol = await market_data.get_or_create_symbol(privileged_session, "EURUSD")
    privileged_session.add(
        Recommendation(
            tenant_id=org.id,
            workspace_id=ctx.workspace_id,
            symbol_id=symbol.id,
            direction=RecommendationDirection.BUY,
            status=RecommendationStatus.READY,
            confidence_calibrated=Decimal("0.6"),
        )
    )
    await privileged_session.commit()

    await clear_rls_session_context(db_session)
    result = await db_session.execute(select(Recommendation))
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_rls_blocks_cross_workspace_reads(
    db_session: AsyncSession, privileged_session: AsyncSession
) -> None:
    user_a, org_a, _ = await seed_user_org(db_session, email="rls-a@example.com", slug="rls-a")
    user_b, org_b, _ = await seed_user_org(db_session, email="rls-b@example.com", slug="rls-b")
    await db_session.commit()

    ctx_a = await resolve_tenant_context(db_session, user_a.id)
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    assert ctx_a.workspace_id is not None
    assert ctx_b.workspace_id is not None

    symbol = await market_data.get_or_create_symbol(privileged_session, "EURUSD")
    await set_rls_session_context(
        privileged_session,
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
    )
    privileged_session.add(
        Recommendation(
            tenant_id=org_b.id,
            workspace_id=ctx_b.workspace_id,
            symbol_id=symbol.id,
            direction=RecommendationDirection.BUY,
            status=RecommendationStatus.READY,
            confidence_calibrated=Decimal("0.6"),
        )
    )
    privileged_session.add_all(
        [
            Lesson(
                tenant_id=org_b.id,
                workspace_id=ctx_b.workspace_id,
                statement="Workspace B lesson",
                conditions_json={},
            ),
            AgentMemory(
                tenant_id=org_b.id,
                workspace_id=ctx_b.workspace_id,
                memory_type=MemoryType.SEMANTIC,
                key="symbol:EURUSD",
                content_json={"note": "secret"},
            ),
            StrategyStat(
                tenant_id=org_b.id,
                workspace_id=ctx_b.workspace_id,
                strategy_code="DEFAULT",
                setup_type="ANY",
                regime_bucket="ANY",
                session_bucket="ANY",
                volatility_bucket="ANY",
                metadata_json={},
            ),
            OandaConnection(
                tenant_id=org_b.id,
                workspace_id=ctx_b.workspace_id,
                account_id="101-001-1",
            ),
        ]
    )
    await privileged_session.commit()

    await set_rls_session_context(
        db_session,
        tenant_id=org_a.id,
        workspace_id=ctx_a.workspace_id,
        user_id=user_a.id,
    )

    async def count(model: type[Any]) -> int:
        result: Any = await db_session.execute(select(model))
        return len(result.scalars().all())

    assert await count(Recommendation) == 0
    assert await count(Lesson) == 0
    assert await count(AgentMemory) == 0
    assert await count(StrategyStat) == 0
    assert await count(OandaConnection) == 0


@pytest.mark.asyncio
async def test_api_list_recommendations_enforces_rls(
    db_session: AsyncSession, privileged_session: AsyncSession
) -> None:
    import uuid
    from collections.abc import AsyncGenerator

    from app.infrastructure.database import get_db_session

    user_a, org_a, _ = await seed_user_org(db_session, email="api-a@example.com", slug="api-a")
    user_b, org_b, _ = await seed_user_org(db_session, email="api-b@example.com", slug="api-b")
    await db_session.commit()
    ctx_a = await resolve_tenant_context(db_session, user_a.id)
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    assert ctx_a.workspace_id is not None and ctx_b.workspace_id is not None

    symbol = await market_data.get_or_create_symbol(privileged_session, "EURUSD")
    await set_rls_session_context(
        privileged_session,
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
    )
    privileged_session.add(
        Recommendation(
            tenant_id=org_b.id,
            workspace_id=ctx_b.workspace_id,
            symbol_id=symbol.id,
            direction=RecommendationDirection.SELL,
            status=RecommendationStatus.READY,
            confidence_calibrated=Decimal("0.55"),
        )
    )
    await privileged_session.commit()

    async def _provide_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _provide_session

    async def _user_a() -> uuid.UUID:
        return user_a.id

    app.dependency_overrides[get_current_user_id] = _user_a
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/recommendations",
            headers={
                "X-Tenant-Id": str(org_a.id),
                "X-Workspace-Id": str(ctx_a.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["items"] == []


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

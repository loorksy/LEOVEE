from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.infrastructure.database import get_db_session
from app.main import app
from app.models.memory import AgentMemory, Lesson, MemoryType
from app.services import watchlist_service
from app.services.memory_service import store_memory
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_watchlist_crud_isolated(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="wl@example.com", slug="wl-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    await bind_workspace_rls(db_session, ctx)
    wl = await watchlist_service.create_watchlist(db_session, ctx, name="FX")
    await watchlist_service.add_symbol(db_session, ctx, watchlist_id=wl.id, symbol_code="EURUSD")
    await db_session.commit()
    lists = await watchlist_service.list_watchlists(db_session, ctx)
    assert len(lists) == 1


@pytest.mark.asyncio
async def test_alert_price_trigger_mock(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="al@example.com", slug="al-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    await bind_workspace_rls(db_session, ctx)

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/alerts",
            json={
                "type": "PRICE",
                "symbol": "EURUSD",
                "condition": {"op": "gte", "price": 1.1},
            },
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
        assert created.status_code == 201
        alert_id = created.json()["id"]
        fired = await client.post(
            f"/api/v1/alerts/{alert_id}/trigger",
            json={"price": 1.2},
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert fired.status_code == 200


@pytest.mark.asyncio
async def test_journal_promote_creates_lesson(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="jn@example.com", slug="jn-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    await bind_workspace_rls(db_session, ctx)

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/journal",
            json={"title": "Session", "notes": "Waited for London open", "lesson": "Patience"},
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
        entry_id = created.json()["id"]
        promoted = await client.post(
            f"/api/v1/journal/{entry_id}/promote",
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert promoted.status_code == 200
    lesson_id = promoted.json()["lesson_id"]
    await bind_workspace_rls(db_session, ctx)
    lesson = await db_session.scalar(select(Lesson).where(Lesson.id == uuid.UUID(lesson_id)))
    assert lesson is not None


@pytest.mark.asyncio
async def test_memory_delete_runs_recompute(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="mem-del@example.com", slug="mem-del")
    ctx = await resolve_tenant_context(db_session, user.id)
    mem = await store_memory(
        db_session,
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        key="symbol:EURUSD",
        content={"note": "delete me", "sample_size": 30},
        memory_type=MemoryType.SEMANTIC,
    )
    await db_session.commit()
    await bind_workspace_rls(db_session, ctx)

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            f"/api/v1/memory/{mem.id}",
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["recompute"]["embeddings_indexed"] >= 0
    await bind_workspace_rls(db_session, ctx)
    gone = await db_session.scalar(select(AgentMemory).where(AgentMemory.id == mem.id))
    assert gone is None

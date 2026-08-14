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
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.mcp import McpAuditEvent
from app.models.usage_record import UsageRecord
from app.services import recommendation_service
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_mcp_workspace_escape_on_recommendation(db_session: AsyncSession) -> None:
    user_a, org_a, _ = await seed_user_org(db_session, email="mcp-a@example.com", slug="mcp-a")
    user_b, org_b, _ = await seed_user_org(db_session, email="mcp-b@example.com", slug="mcp-b")
    await db_session.commit()
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    await bind_workspace_rls(db_session, ctx_b)
    rec_b = await recommendation_service.create_recommendation(
        db_session,
        ctx_b,
        symbol_code="XAUUSD",
        direction=RecommendationDirection.SELL,
        status=RecommendationStatus.ACTIVE,
    )
    await db_session.commit()
    ctx_a = await resolve_tenant_context(db_session, user_a.id)

    async def override_user() -> uuid.UUID:
        return user_a.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/mcp/tools/invoke",
            json={
                "tool": "recommendation.get",
                "arguments": {"recommendation_id": str(rec_b.id)},
            },
            headers={
                "X-Tenant-Id": str(org_a.id),
                "X-Workspace-Id": str(ctx_a.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mcp_invoke_writes_audit_and_usage(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="mcp-use@example.com", slug="mcp-use")
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/mcp/tools/invoke",
            json={"tool": "workspace.get_context", "arguments": {}},
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200

    await bind_workspace_rls(db_session, ctx)
    audits = await db_session.execute(select(McpAuditEvent))
    assert len(audits.scalars().all()) >= 1
    usage = await db_session.execute(select(UsageRecord).where(UsageRecord.metric == "mcp.call"))
    assert len(usage.scalars().all()) >= 1


@pytest.mark.asyncio
async def test_mcp_app_manifest_includes_csp() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/mcp/apps/leovee-chart-app/manifest")
    assert response.status_code == 200
    assert "contentSecurityPolicy" in response.json()
    assert "Content-Security-Policy" in response.headers
    assert response.json()["api"]["auth"] == "bearer"

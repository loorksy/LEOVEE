import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.infrastructure.database import get_db_session
from app.main import app
from app.models.enums import RecommendationDirection
from app.services import recommendation_service
from app.services.workspace_service import create_default_workspace
from app.tests.conftest import seed_user_org


@pytest.fixture
def workspace_app(db_session: AsyncSession) -> Any:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session_override
    yield app
    app.dependency_overrides.clear()


async def test_workspace_isolation_between_users(
    workspace_app: Any,
    db_session: AsyncSession,
) -> None:
    user_a, org_a, _ = await seed_user_org(db_session, email="a@example.com", slug="org-a-ws")
    user_b, org_b, _ = await seed_user_org(db_session, email="b@example.com", slug="org-b-ws")

    ws_b = await create_default_workspace(
        db_session,
        tenant_id=org_b.id,
        owner_user_id=user_b.id,
        name="Private B",
    )
    await db_session.commit()

    async def _user_a() -> uuid.UUID:
        return user_a.id

    workspace_app.dependency_overrides[get_current_user_id] = _user_a
    transport = ASGITransport(app=workspace_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get(
            f"/api/v1/workspaces/{ws_b.id}",
            headers={"X-Tenant-Id": str(org_a.id)},
        )
        assert denied.status_code == 404


async def test_recommendations_scoped_to_workspace(
    db_session: AsyncSession,
) -> None:
    user, org, _ = await seed_user_org(db_session, email="rec@example.com", slug="rec-org")
    from app.core.tenant import resolve_tenant_context

    ctx = await resolve_tenant_context(db_session, user.id)
    rec = await recommendation_service.create_recommendation(
        db_session,
        ctx,
        symbol_code="EURUSD",
        direction=RecommendationDirection.BUY,
    )
    await db_session.commit()

    other_ws = await create_default_workspace(
        db_session,
        tenant_id=org.id,
        owner_user_id=user.id,
        name="Alt",
    )
    from app.core.tenant import TenantContext

    alt_ctx = TenantContext(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        organization_member_id=ctx.organization_member_id,
        role=ctx.role,
        workspace_id=other_ws.id,
        workspace_member_id=ctx.workspace_member_id,
    )
    foreign = await recommendation_service.get_recommendation(db_session, alt_ctx, rec.id)
    assert foreign is None

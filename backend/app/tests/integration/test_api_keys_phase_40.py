from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.tenant import resolve_tenant_context
from app.infrastructure.database import get_db_session
from app.main import app
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_create_and_list_api_keys(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="keys@example.com", slug="keys-ws")
    ctx = await resolve_tenant_context(db_session, user.id)
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/api-keys",
            json={"name": "CI bot", "scopes": ["workspace.read"]},
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
        listed = await client.get(
            "/api/v1/api-keys",
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert created.status_code == 200
    assert created.json()["api_key"].startswith("lvk_")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

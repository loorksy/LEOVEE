import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.main import app
from app.tests.conftest import seed_user_org


@pytest.fixture
def test_app(db_session: AsyncSession) -> Any:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session_override
    get_settings.cache_clear()
    yield app
    app.dependency_overrides.clear()
    get_settings.cache_clear()


async def test_me_tenant_endpoint(test_app: Any, db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session)

    async def _user_override() -> uuid.UUID:
        return user.id

    test_app.dependency_overrides[get_current_user_id] = _user_override

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/me/tenant")

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == str(org.id)
    assert body["user_id"] == str(user.id)


async def test_me_tenant_rejects_foreign_tenant_header(
    test_app: Any, db_session: AsyncSession
) -> None:
    user, _, _ = await seed_user_org(db_session)

    async def _user_override() -> uuid.UUID:
        return user.id

    test_app.dependency_overrides[get_current_user_id] = _user_override

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/me/tenant",
            headers={"X-Tenant-Id": str(uuid.uuid4())},
        )

    assert response.status_code == 403

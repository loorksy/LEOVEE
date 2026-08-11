from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.core.tenant import resolve_tenant_context
from app.infrastructure.database import get_db_session
from app.main import app
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_news_reports_provider_not_configured(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    get_settings.cache_clear()

    user, org, _ = await seed_user_org(db_session, email="news-cfg@example.com", slug="news-cfg")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    headers = {
        "X-Tenant-Id": str(org.id),
        "X-Workspace-Id": str(ctx.workspace_id),
    }
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/news", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["provider_configured"] is False
        assert body["provider_status"] == "not_configured"
        assert body["items"] == []
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_providers_status_shape(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OANDA_API_TOKEN", "practice-token")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "001-001-123")
    monkeypatch.setenv("OANDA_ENVIRONMENT", "practice")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    get_settings.cache_clear()

    user, org, _ = await seed_user_org(db_session, email="prov@example.com", slug="prov-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    headers = {
        "X-Tenant-Id": str(org.id),
        "X-Workspace-Id": str(ctx.workspace_id),
    }
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/providers/status", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["oanda"]["configured"] is True
        assert body["oanda"]["environment"] == "practice"
        assert body["finnhub"]["status"] == "not_configured"
        assert body["anthropic"]["configured"] is True
        assert body["openai"]["configured"] is True
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

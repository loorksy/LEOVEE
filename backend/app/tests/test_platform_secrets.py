from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.core.tenant import resolve_tenant_context
from app.infrastructure.database import get_db_session
from app.infrastructure.seed import ensure_platform_seed
from app.main import create_app
from app.models.platform_secret import PlatformSecret
from app.models.rbac import Role
from app.models.workspace_member import WorkspaceMember
from app.services.platform_secrets import (
    PlatformSecretError,
    encrypt_secret,
    load_runtime_overrides,
    set_runtime_overrides,
    upsert_secrets,
    validate_secret_update,
)
from app.tests.conftest import seed_user_org

app = create_app()


@pytest.fixture(autouse=True)
def _clear_runtime_secrets() -> Iterator[None]:
    set_runtime_overrides({})
    get_settings.cache_clear()
    yield
    set_runtime_overrides({})
    get_settings.cache_clear()


async def _set_workspace_role(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_code: str,
) -> None:
    await ensure_platform_seed(session)
    role = await session.scalar(select(Role).where(Role.code == role_code))
    assert role is not None
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    assert member is not None
    member.role_id = role.id
    await session.flush()


def test_validate_rejects_live_oanda_environment() -> None:
    with pytest.raises(PlatformSecretError, match="practice"):
        validate_secret_update("OANDA_ENVIRONMENT", "live")


def test_encrypt_roundtrip() -> None:
    token = encrypt_secret("hello-secret")
    assert token != "hello-secret"


@pytest.mark.asyncio
async def test_upsert_and_runtime_overlay(db_session: AsyncSession) -> None:
    items = await upsert_secrets(
        db_session,
        updates={
            "OPENAI_API_KEY": "sk-test-openai",
            "OANDA_ENVIRONMENT": "practice",
        },
        actor_user_id=None,
    )
    await db_session.commit()
    assert any(i.key == "OPENAI_API_KEY" and i.configured for i in items)

    row = await db_session.scalar(
        select(PlatformSecret).where(PlatformSecret.key == "OPENAI_API_KEY")
    )
    assert row is not None
    assert row.ciphertext != "sk-test-openai"

    get_settings.cache_clear()
    assert get_settings().openai_api_key == "sk-test-openai"
    assert get_settings().oanda_environment == "practice"

    set_runtime_overrides({})
    get_settings.cache_clear()
    loaded = await load_runtime_overrides(db_session)
    assert loaded["OPENAI_API_KEY"] == "sk-test-openai"
    assert get_settings().openai_api_key == "sk-test-openai"


@pytest.mark.asyncio
async def test_admin_secrets_api_requires_admin_and_masks_values(
    db_session: AsyncSession,
) -> None:
    user, org, _ = await seed_user_org(
        db_session, email="secrets-admin@example.com", slug="secrets-admin"
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await _set_workspace_role(
        db_session,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        role_code="SUPER_ADMIN",
    )
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
            listed = await client.get("/api/v1/admin/secrets", headers=headers)
            assert listed.status_code == 200, listed.text
            body = listed.json()
            assert "OPENAI_API_KEY" in body["managed_keys"]
            assert all("ciphertext" not in item for item in body["items"])

            denied_live = await client.put(
                "/api/v1/admin/secrets",
                headers=headers,
                json={"secrets": {"OANDA_ENVIRONMENT": "live"}},
            )
            assert denied_live.status_code == 400

            ok = await client.put(
                "/api/v1/admin/secrets",
                headers=headers,
                json={"secrets": {"ANTHROPIC_API_KEY": "sk-ant-test"}},
            )
            assert ok.status_code == 200, ok.text
            assert get_settings().anthropic_api_key == "sk-ant-test"
            assert "sk-ant-test" not in ok.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_user_role_cannot_read_secrets(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(
        db_session, email="secrets-user@example.com", slug="secrets-user"
    )
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
            listed = await client.get("/api/v1/admin/secrets", headers=headers)
            assert listed.status_code == 403
    finally:
        app.dependency_overrides.clear()

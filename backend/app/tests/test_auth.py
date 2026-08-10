import re
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.rate_limit import reset_rate_limiter_for_tests
from app.main import app
from app.providers.email.console import clear_console_outbox, get_console_outbox


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    clear_console_outbox()
    reset_rate_limiter_for_tests()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _extract_token_from_outbox() -> str:
    messages = get_console_outbox()
    assert messages
    body = messages[-1].text_body or ""
    match = re.search(r"token=([A-Za-z0-9_-]+)", body)
    assert match
    return match.group(1)


async def test_signup_verify_login_and_tenant(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    signup = await api_client.post(
        "/api/v1/auth/signup",
        json={"email": "trader@example.com", "password": "securepassword1"},
    )
    assert signup.status_code == 200
    tokens = signup.json()
    assert "access_token" in tokens

    me_unverified = await api_client.get(
        "/api/v1/me/tenant",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_unverified.status_code == 403

    login_blocked = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "trader@example.com", "password": "securepassword1"},
    )
    assert login_blocked.status_code == 403

    verify_token = _extract_token_from_outbox()
    verify = await api_client.post("/api/v1/auth/verify-email", json={"token": verify_token})
    assert verify.status_code == 200

    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "trader@example.com", "password": "securepassword1"},
    )
    assert login.status_code == 200
    access = login.json()["access_token"]

    tenant = await api_client.get(
        "/api/v1/me/tenant",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert tenant.status_code == 200
    assert tenant.json()["role"] == "ORG_OWNER"


async def test_refresh_rotation_and_logout(api_client: AsyncClient) -> None:
    await api_client.post(
        "/api/v1/auth/signup",
        json={"email": "refresh@example.com", "password": "securepassword1"},
    )
    verify_token = _extract_token_from_outbox()
    await api_client.post("/api/v1/auth/verify-email", json={"token": verify_token})

    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "securepassword1"},
    )
    refresh_token = login.json()["refresh_token"]

    refreshed = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["refresh_token"]
    assert new_refresh != refresh_token

    old_refresh = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert old_refresh.status_code == 401

    await api_client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh})
    logged_out = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    assert logged_out.status_code == 401


async def test_login_rate_limit(api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RATE_LIMIT_LOGIN", "2")
    get_settings.cache_clear()

    for _ in range(2):
        response = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrongpassword12"},
        )
        assert response.status_code == 401

    blocked = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrongpassword12"},
    )
    assert blocked.status_code == 429

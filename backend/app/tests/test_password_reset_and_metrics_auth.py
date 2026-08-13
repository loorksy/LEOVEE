from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.auth_service as auth_service
from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.rate_limit import reset_rate_limiter_for_tests
from app.main import app
from app.providers.email.console import (
    ConsoleEmailProvider,
    clear_console_outbox,
    get_console_outbox,
)
from app.providers.email.factory import get_email_provider


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    clear_console_outbox()
    reset_rate_limiter_for_tests()
    get_email_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_email_provider.cache_clear()


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


@pytest.mark.asyncio
async def test_password_reset_flow(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Signup only sends a verification email when Resend is configured;
    # otherwise the account is auto-verified and the outbox stays empty. Set the
    # key to take that branch, but deliver through the console provider so the
    # token is capturable — the same arrangement test_auth.py uses.
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    get_settings.cache_clear()
    get_email_provider.cache_clear()
    monkeypatch.setattr(auth_service, "get_email_provider", lambda: ConsoleEmailProvider())
    clear_console_outbox()

    signup = await api_client.post(
        "/api/v1/auth/signup",
        json={"email": "resetme@example.com", "password": "oldpassword12"},
    )
    assert signup.status_code == 200
    verify_token = _extract_token_from_outbox()
    await api_client.post("/api/v1/auth/verify-email", json={"token": verify_token})
    clear_console_outbox()

    requested = await api_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "resetme@example.com"},
    )
    assert requested.status_code == 200
    reset_token = _extract_token_from_outbox()

    confirmed = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "newpassword34"},
    )
    assert confirmed.status_code == 200

    old_login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@example.com", "password": "oldpassword12"},
    )
    assert old_login.status_code == 401

    new_login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@example.com", "password": "newpassword34"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_rate_limit(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_RATE_LIMIT_PASSWORD_RESET", "2")
    get_settings.cache_clear()
    for _ in range(2):
        response = await api_client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "rate@example.com"},
        )
        assert response.status_code == 200
    blocked = await api_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "rate@example.com"},
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_metrics_requires_bearer_in_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "metrics-secret")
    get_settings.cache_clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/metrics")
        allowed = await client.get(
            "/metrics",
            headers={"Authorization": "Bearer metrics-secret"},
        )
    get_settings.cache_clear()
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert "leovee_up" in allowed.text

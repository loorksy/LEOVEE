from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.tenant import resolve_tenant_context
from app.infrastructure.database import get_db_session
from app.main import app
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.services import market_data
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_replay_preview_api(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(
        db_session,
        email="replay-api@example.com",
        slug="replay-api",
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    symbol = await market_data.get_or_create_symbol(db_session, "EURUSD")
    db_session.add(
        Candle(
            symbol_id=symbol.id,
            timeframe=Timeframe.H1,
            ts=datetime(2024, 6, 1, 10, tzinfo=UTC),
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
        )
    )
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/replay/preview",
            json={
                "symbol": "EURUSD",
                "timeframe": "H1",
                "as_of": "2024-06-01T15:00:00+00:00",
            },
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["candle_count"] >= 1
    assert body["recall"]["counts"]["memories"] >= 0

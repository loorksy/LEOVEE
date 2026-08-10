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
from app.models.conversation import Conversation, ConversationMode
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.memory import MemoryType
from app.services import recommendation_service
from app.services.memory_service import store_memory
from app.tests.conftest import seed_user_org
from app.tests.doubles.llm import FakeLLMProvider


@pytest.mark.asyncio
async def test_chat_message_injects_recall(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, org, _ = await seed_user_org(
        db_session,
        email="chat-recall@example.com",
        slug="chat-recall",
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await store_memory(
        db_session,
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        key="symbol:EURUSD",
        content={"bias": "bullish", "sample_size": 25},
        memory_type=MemoryType.SEMANTIC,
    )
    conv = Conversation(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        title="Recall",
        symbol="EURUSD",
        mode=ConversationMode.ANALYZE,
    )
    db_session.add(conv)
    await db_session.commit()

    monkeypatch.setattr("app.api.routes.chat.get_llm_provider", lambda: FakeLLMProvider())

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/conversations/{conv.id}/messages",
            json={"content": "Please analyze EURUSD"},
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["recall"]["count"] >= 1
    assert any(a["type"] == "RUN_ANALYSIS" for a in body["actions"])


@pytest.mark.asyncio
async def test_recommendation_terminal_status_triggers_outcome(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="rec-term@example.com", slug="rec-term")
    ctx = await resolve_tenant_context(db_session, user.id)
    rec = await recommendation_service.create_recommendation(
        db_session,
        ctx,
        symbol_code="EURUSD",
        direction=RecommendationDirection.BUY,
        status=RecommendationStatus.READY,
    )
    await recommendation_service.transition_recommendation_status(
        db_session,
        ctx,
        rec.id,
        new_status=RecommendationStatus.ACTIVE,
    )
    updated = await recommendation_service.transition_recommendation_status(
        db_session,
        ctx,
        rec.id,
        new_status=RecommendationStatus.TARGET_REACHED,
        facts={"test": True},
    )
    assert updated is not None
    assert updated.status == RecommendationStatus.TARGET_REACHED

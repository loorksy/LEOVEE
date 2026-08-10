"""Spec §100 — multi-tenant security regression suite."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.infrastructure.rls import set_rls_session_context
from app.models.api_key import ApiKey
from app.models.conversation import Conversation, ConversationMode
from app.services import api_key_service
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_s100_cross_workspace_conversations_hidden(
    db_session: AsyncSession,
    privileged_session: AsyncSession,
) -> None:
    user_a, org_a, _ = await seed_user_org(db_session, email="s100-ca@example.com", slug="s100-ca")
    user_b, org_b, _ = await seed_user_org(db_session, email="s100-cb@example.com", slug="s100-cb")
    await db_session.commit()
    ctx_a = await resolve_tenant_context(db_session, user_a.id)
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    assert ctx_a.workspace_id and ctx_b.workspace_id

    await set_rls_session_context(
        privileged_session,
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
    )
    privileged_session.add(
        Conversation(
            tenant_id=org_b.id,
            workspace_id=ctx_b.workspace_id,
            user_id=user_b.id,
            title="Secret chat",
            mode=ConversationMode.ANALYZE,
        )
    )
    await privileged_session.commit()

    await set_rls_session_context(
        db_session,
        tenant_id=org_a.id,
        workspace_id=ctx_a.workspace_id,
        user_id=user_a.id,
    )
    result = await db_session.execute(select(Conversation))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_s100_cross_workspace_api_keys_hidden(
    db_session: AsyncSession,
    privileged_session: AsyncSession,
) -> None:
    user_a, org_a, _ = await seed_user_org(db_session, email="s100-ka@example.com", slug="s100-ka")
    user_b, org_b, _ = await seed_user_org(db_session, email="s100-kb@example.com", slug="s100-kb")
    await db_session.commit()
    ctx_a = await resolve_tenant_context(db_session, user_a.id)
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    assert ctx_a.workspace_id and ctx_b.workspace_id

    await set_rls_session_context(
        privileged_session,
        tenant_id=org_b.id,
        workspace_id=ctx_b.workspace_id,
        user_id=user_b.id,
    )
    await api_key_service.create_api_key(
        privileged_session,
        ctx_b,
        name="Workspace B key",
    )
    await privileged_session.commit()

    await set_rls_session_context(
        db_session,
        tenant_id=org_a.id,
        workspace_id=ctx_a.workspace_id,
        user_id=user_a.id,
    )
    result = await db_session.execute(select(ApiKey))
    assert result.scalars().all() == []


def test_s100_api_key_scope_enforcement() -> None:
    with pytest.raises(api_key_service.ApiKeyError) as exc:
        api_key_service.assert_scopes(["workspace.read"], "markets.read")
    assert exc.value.code == "scope_denied"

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.conversation import Conversation, ConversationMode, Message, MessageRole
from app.services.chat_service import maybe_refresh_conversation_summary
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_conversation_summary_after_threshold(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session)
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    conv = Conversation(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        title="Summary test",
        mode=ConversationMode.CHAT,
    )
    db_session.add(conv)
    await db_session.flush()
    for i in range(11):
        db_session.add(
            Message(
                tenant_id=org.id,
                workspace_id=ctx.workspace_id,
                conversation_id=conv.id,
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=f"message-{i}",
            )
        )
    await db_session.flush()
    summary = await maybe_refresh_conversation_summary(db_session, conv)
    assert summary is not None
    assert "message-" in summary

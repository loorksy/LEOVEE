from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.conversation import Conversation, ConversationMode
from app.services import chat_service
from app.tests.conftest import seed_user_org
from app.tests.doubles.llm import FakeLLMProvider

_ARTIFACT_REPLY = (
    "Here is the daily gold bias.\n\n"
    "```artifact\n"
    '{"type": "agent-candlestick-chart-artifact", "title": "XAUUSD M15"}\n'
    '{"series": [{"t": 1, "o": 2000, "h": 2005, "l": 1998, "c": 2003}]}\n'
    "```\n\n"
    "And the levels:\n\n"
    "```artifact\n"
    '{"type": "portfolio-summary"}\n'
    "| level | price |\n| ----- | ----- |\n| entry | 2001 |\n"
    "```\n"
)


async def _conversation(
    session: AsyncSession, *, email: str, slug: str
) -> tuple[TenantContext, Conversation]:
    user, org, _ = await seed_user_org(session, email=email, slug=slug)
    ctx = await resolve_tenant_context(session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(session, ctx)
    conversation = Conversation(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        title="Artifacts",
        mode=ConversationMode.CHAT,
        symbol="XAUUSD",
    )
    session.add(conversation)
    await session.flush()
    return ctx, conversation


@pytest.mark.asyncio
async def test_chat_turn_stamps_artifacts_into_content_json(db_session: AsyncSession) -> None:
    """An artifact fence in the model reply is parsed and family-stamped on the row.

    The frontend renders from the structured ``content_json.artifacts`` rather
    than re-parsing prose on every paint, so the mapping from open-ended ``type``
    to a real renderer ``family`` must be decided once, at persistence.
    """
    ctx, conversation = await _conversation(
        db_session, email="artifacts@example.com", slug="artifacts"
    )
    llm = FakeLLMProvider(content=_ARTIFACT_REPLY)

    result = await chat_service.run_chat_turn(
        db_session,
        ctx,
        conversation,
        user_content="Give me the gold bias",
        llm=llm,
    )

    content_json = result.assistant_message.content_json or {}
    artifacts = content_json["artifacts"]
    assert [a["family"] for a in artifacts] == ["chart", "table"]
    assert [a["type"] for a in artifacts] == ["candlestick-chart", "portfolio-summary"]
    # The `agent-…-artifact` wrapper is stripped, and the title survives.
    assert artifacts[0]["title"] == "XAUUSD M15"
    # The payload is carried verbatim for the renderer, header line excluded.
    assert '"series"' in artifacts[0]["content"]
    assert "| entry | 2001 |" in artifacts[1]["content"]


@pytest.mark.asyncio
async def test_chat_turn_without_artifacts_persists_empty_list(db_session: AsyncSession) -> None:
    """Plain prose is the common case: the key is present and empty, never missing."""
    ctx, conversation = await _conversation(
        db_session, email="no-artifacts@example.com", slug="no-artifacts"
    )
    llm = FakeLLMProvider(content="Just prose, no fences here.")

    result = await chat_service.run_chat_turn(
        db_session,
        ctx,
        conversation,
        user_content="Say something",
        llm=llm,
    )

    content_json = result.assistant_message.content_json or {}
    assert content_json["artifacts"] == []

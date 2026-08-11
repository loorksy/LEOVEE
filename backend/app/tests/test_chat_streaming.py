from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.providers.llm.anthropic import AnthropicProvider
from app.providers.llm.base import LLMMessage, LLMStreamChunk
from app.providers.llm.errors import LLMError
from app.providers.llm.openai import OpenAIProvider
from app.services.chat_stream import collect_stream_chunks, iter_chat_turn_stream
from app.tests.doubles.llm import FakeLLMProvider


class _AsyncIter:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def __aiter__(self) -> _AsyncIter:
        self._iter = iter(self._items)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FlakyThenOkProvider:
    """Fails mid-stream once, then a fallback can succeed."""

    def __init__(self, *, fail: bool = True, label: str = "primary") -> None:
        self.fail = fail
        self.label = label
        self.calls = 0

    async def complete(self, messages: list[LLMMessage], **kwargs: Any) -> Any:
        raise NotImplementedError

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        self.calls += 1
        yield LLMStreamChunk(text="partial-", model=self.label, provider=self.label)
        if self.fail:
            raise LLMError("boom mid-stream", code="llm_upstream", retryable=True)
        yield LLMStreamChunk(text="ok", model=self.label, provider=self.label)
        yield LLMStreamChunk(
            text="",
            model=self.label,
            provider=self.label,
            done=True,
            usage={"total_tokens": 3},
        )


class SlowProvider:
    async def complete(self, messages: list[LLMMessage], **kwargs: Any) -> Any:
        raise NotImplementedError

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        yield LLMStreamChunk(text="hi", model="slow", provider="slow")
        await asyncio.sleep(60)
        yield LLMStreamChunk(text="", model="slow", provider="slow", done=True)


@pytest.mark.asyncio
async def test_streaming_parity_fake_providers() -> None:
    a = FakeLLMProvider(content="alpha beta")
    b = FakeLLMProvider(content="alpha beta")
    msgs = [LLMMessage(role="user", content="hi")]
    text_a, chunks_a = await collect_stream_chunks(a, msgs)
    text_b, chunks_b = await collect_stream_chunks(b, msgs)
    assert text_a.strip() == text_b.strip()
    assert chunks_a[-1].done and chunks_b[-1].done


@pytest.mark.asyncio
async def test_streaming_parity_openai_and_anthropic_providers() -> None:
    """Both real providers must emit the same token text + a terminal done chunk."""
    oai_client = MagicMock()
    oai_client.chat.completions.create = AsyncMock(
        return_value=_AsyncIter(
            [
                SimpleNamespace(
                    model="gpt",
                    usage=None,
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="hello "))],
                ),
                SimpleNamespace(
                    model="gpt",
                    usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="world"))],
                ),
            ]
        )
    )
    oai = OpenAIProvider("test-key", client=oai_client)
    ant_client = MagicMock()
    ant_client.messages.create = AsyncMock(
        return_value=_AsyncIter(
            [
                SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text="hello ")),
                SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text="world")),
                SimpleNamespace(
                    type="message_delta",
                    usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                ),
            ]
        )
    )
    ant = AnthropicProvider("test-key", client=ant_client)
    msgs = [LLMMessage(role="user", content="hi")]
    text_oai, chunks_oai = await collect_stream_chunks(oai, msgs)
    text_ant, chunks_ant = await collect_stream_chunks(ant, msgs)
    assert text_oai == text_ant == "hello world"
    assert chunks_oai[-1].done and chunks_ant[-1].done
    assert chunks_oai[-1].provider == "openai"
    assert chunks_ant[-1].provider == "anthropic"


@pytest.mark.asyncio
async def test_mid_stream_failure_falls_back_without_duplicate(
    db_session: Any,
) -> None:
    from sqlalchemy import select

    from app.core.tenant import resolve_tenant_context
    from app.core.tenant_rls import bind_workspace_rls
    from app.models.conversation import Conversation, ConversationMode, Message, MessageRole
    from app.tests.conftest import seed_user_org

    user, org, _ = await seed_user_org(db_session, email="stream@example.com", slug="stream-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    conv = Conversation(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        title="Stream",
        symbol="EURUSD",
        mode=ConversationMode.CHAT,
    )
    db_session.add(conv)
    await db_session.flush()

    primary = FlakyThenOkProvider(fail=True, label="primary")
    fallback = FlakyThenOkProvider(fail=False, label="fallback")
    events: list[dict[str, Any]] = []
    async for event in iter_chat_turn_stream(
        db_session,
        ctx,
        conv,
        user_content="hello stream",
        llm=primary,
        fallback_llm=fallback,
    ):
        events.append(event)

    kinds = [e["event"] for e in events]
    assert "stream_reset" in kinds
    assert kinds.count("done") == 1
    assert "error" not in kinds
    # Partial primary token must not appear in the final assistant content.
    done = next(e for e in events if e["event"] == "done")
    assistant_id = done["assistant_message_id"]
    row = await db_session.scalar(select(Message).where(Message.id == assistant_id))
    assert row is not None
    # Fallback starts clean after stream_reset — primary "partial-" is discarded.
    assert row.content == "partial-ok"
    assert row.provider == "fallback"
    token_texts = [e["data"] for e in events if e["event"] == "token"]
    # Client may have seen primary tokens before reset; they must not be persisted.
    assert "partial-" in token_texts
    assert events[kinds.index("stream_reset")]["reason"] == "provider_failed"
    # Exactly one assistant message (no truncated primary row).
    assistants = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conv.id,
            Message.role == MessageRole.ASSISTANT,
        )
    )
    assert len(assistants.scalars().all()) == 1


@pytest.mark.asyncio
async def test_client_disconnect_does_not_persist_assistant(
    db_session: Any,
) -> None:
    from sqlalchemy import select

    from app.core.tenant import resolve_tenant_context
    from app.core.tenant_rls import bind_workspace_rls
    from app.models.conversation import Conversation, ConversationMode, Message, MessageRole
    from app.tests.conftest import seed_user_org

    user, org, _ = await seed_user_org(db_session, email="disc@example.com", slug="disc-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    conv = Conversation(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        title="Disc",
        mode=ConversationMode.CHAT,
    )
    db_session.add(conv)
    await db_session.flush()

    agen = cast(
        AsyncGenerator[dict[str, Any], None],
        iter_chat_turn_stream(
            db_session,
            ctx,
            conv,
            user_content="bye",
            llm=SlowProvider(),
        ),
    )
    # Consume until first token, then cancel via generator close protocol.
    first = await agen.__anext__()
    assert first["event"] == "recall"
    await agen.__anext__()  # user_message
    token = await agen.__anext__()
    assert token["event"] == "token"
    with pytest.raises(asyncio.CancelledError):
        await agen.athrow(asyncio.CancelledError)

    assistants = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conv.id,
            Message.role == MessageRole.ASSISTANT,
        )
    )
    assert list(assistants.scalars().all()) == []
    users = await db_session.execute(
        select(Message).where(
            Message.conversation_id == conv.id,
            Message.role == MessageRole.USER,
        )
    )
    assert len(users.scalars().all()) == 1


@pytest.mark.asyncio
async def test_partial_response_events_order() -> None:
    provider = FakeLLMProvider(content="one two three")
    text, chunks = await collect_stream_chunks(provider, [LLMMessage(role="user", content="x")])
    assert "one" in text
    assert chunks[0].done is False
    assert chunks[-1].done is True

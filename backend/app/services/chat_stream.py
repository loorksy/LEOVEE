"""Provider-native chat streaming with clean failure / disconnect semantics."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.artifacts import stamp_artifacts
from app.core.datetime_utils import utc_now
from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message, MessageRole
from app.providers.llm.base import LLMMessage, LLMProvider, LLMStreamChunk
from app.providers.llm.errors import LLMError
from app.services import chat_service, entitlement_service
from app.services.chat_actions import propose_chat_actions


@dataclass
class StreamState:
    user_message: Message
    recall: dict[str, Any]
    actions: list[dict[str, Any]]
    llm_messages: list[LLMMessage]
    parts: list[str] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    assistant_message: Message | None = None
    finalized: bool = False


async def prepare_chat_stream(
    session: AsyncSession,
    tenant: TenantContext,
    conversation: Conversation,
    *,
    user_content: str,
) -> StreamState:
    """Persist the user message and build recall/history before tokens start."""
    await entitlement_service.check_metric_limit(session, tenant, "chat.send")
    recall = await chat_service.build_recall_bundle(
        session,
        tenant,
        symbol=conversation.symbol,
        query=user_content,
    )
    await chat_service.maybe_refresh_conversation_summary(session, conversation)
    history = await chat_service.load_conversation_messages(session, conversation.id)
    llm_messages = chat_service.build_llm_messages(
        conversation=conversation,
        recall=recall,
        history=history,
        user_content=user_content,
    )
    actions = propose_chat_actions(
        mode=conversation.mode,
        user_content=user_content,
        symbol=conversation.symbol,
    )
    user_msg = Message(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=user_content,
        symbol_context=conversation.symbol,
    )
    session.add(user_msg)
    conversation.last_message_at = utc_now()
    await session.flush()
    return StreamState(
        user_message=user_msg,
        recall=recall,
        actions=actions,
        llm_messages=llm_messages,
    )


async def _consume_provider_stream(
    provider: LLMProvider,
    messages: list[LLMMessage],
    state: StreamState,
) -> AsyncIterator[dict[str, Any]]:
    """Yield token events from a single provider stream into ``state.parts``."""
    async for chunk in provider.stream(messages):
        if chunk.text:
            state.parts.append(chunk.text)
            state.model = chunk.model or state.model
            state.provider = chunk.provider or state.provider
            yield {"event": "token", "data": chunk.text}
        if chunk.done:
            state.usage = chunk.usage or state.usage
            state.model = chunk.model or state.model
            state.provider = chunk.provider or state.provider


async def finalize_assistant_message(
    session: AsyncSession,
    tenant: TenantContext,
    conversation: Conversation,
    state: StreamState,
) -> Message:
    content = "".join(state.parts)
    # Stamp artifacts on the finished text, not the token stream: a fence spans
    # many chunks, so it can only be parsed once the reply is whole. The `done`
    # event carries these stamped families so the client renders from the
    # server's authoritative parse rather than re-deriving it.
    state.artifacts = stamp_artifacts(content)
    assistant = Message(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=content,
        content_json={
            "recall_count": state.recall.get("count", 0),
            "actions": state.actions,
            "artifacts": state.artifacts,
            "streamed": True,
        },
        model=state.model or None,
        provider=state.provider or None,
        token_usage_json=state.usage or None,
    )
    session.add(assistant)
    conversation.last_message_at = utc_now()
    await session.flush()
    await entitlement_service.record_usage(session, tenant, "chat.send")
    state.assistant_message = assistant
    state.finalized = True
    return assistant


async def iter_chat_turn_stream(
    session: AsyncSession,
    tenant: TenantContext,
    conversation: Conversation,
    *,
    user_content: str,
    llm: LLMProvider,
    fallback_llm: LLMProvider | None = None,
    providers: list[tuple[str, LLMProvider]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream recall + tokens, then persist a single assistant message.

    Failure / disconnect rules:
    - Partial tokens from a failed primary are **discarded** (not persisted).
    - Fallback providers start a clean stream; client receives ``stream_reset``.
    - On cancel/disconnect, no assistant row is written (user message remains).
    - Successful completion writes exactly one assistant message.
    """
    state = await prepare_chat_stream(session, tenant, conversation, user_content=user_content)
    yield {
        "event": "recall",
        "count": state.recall.get("count", 0),
        "label": state.recall.get("label"),
        "symbol": state.recall.get("symbol"),
        "items": state.recall.get("items", []),
    }
    yield {
        "event": "user_message",
        "id": str(state.user_message.id),
    }

    if providers is None:
        chain: list[tuple[str, LLMProvider]] = [("primary", llm)]
        if fallback_llm is not None:
            chain.append(("fallback", fallback_llm))
    else:
        chain = providers

    last_error: Exception | None = None
    for index, (label, provider) in enumerate(chain):
        state.parts.clear()
        state.usage = {}
        try:
            async for event in _consume_provider_stream(provider, state.llm_messages, state):
                yield event
            # Advance OpenRouter free-model cursor after a successful stream.
            if label.startswith("openrouter:"):
                from app.providers.llm.openrouter_catalog import advance_cursor

                advance_cursor(label.split("openrouter:", 1)[-1])
            assistant = await finalize_assistant_message(session, tenant, conversation, state)
            yield {
                "event": "done",
                "assistant_message_id": str(assistant.id),
                "actions": state.actions,
                "artifacts": state.artifacts,
                "provider": state.provider,
                "via": label,
            }
            return
        except asyncio.CancelledError:
            # Client disconnected — do not persist a truncated assistant message.
            raise
        except Exception as exc:  # noqa: BLE001 — normalized for SSE clients
            last_error = exc
            # Discard partial tokens so a fallback cannot produce a duplicated/truncated msg.
            state.parts.clear()
            if label.startswith("openrouter:"):
                from app.providers.llm.openrouter_catalog import advance_cursor

                advance_cursor(label.split("openrouter:", 1)[-1])
            has_more = index < len(chain) - 1
            if has_more:
                yield {
                    "event": "stream_reset",
                    "reason": "provider_failed",
                    "failed_provider": label,
                    "message": str(exc),
                }
                continue
            code = getattr(exc, "code", type(exc).__name__)
            yield {
                "event": "error",
                "code": str(code),
                "message": str(exc) or "LLM stream failed",
                "partial_discarded": True,
            }
            if isinstance(exc, LLMError):
                return
            return

    if last_error is not None:
        yield {
            "event": "error",
            "code": type(last_error).__name__,
            "message": str(last_error),
            "partial_discarded": True,
        }


async def collect_stream_chunks(
    provider: LLMProvider,
    messages: list[LLMMessage],
) -> tuple[str, list[LLMStreamChunk]]:
    """Test helper: drain a provider stream into text + chunks."""
    chunks: list[LLMStreamChunk] = []
    parts: list[str] = []
    async for chunk in provider.stream(messages):
        chunks.append(chunk)
        if chunk.text:
            parts.append(chunk.text)
    return "".join(parts), chunks

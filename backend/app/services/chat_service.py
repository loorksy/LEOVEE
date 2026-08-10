from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message, MessageRole
from app.providers.llm.base import LLMMessage, LLMProvider
from app.services import entitlement_service
from app.services.chat_actions import propose_chat_actions
from app.services.memory_service import retrieve_memories_hybrid

RECALL_CONTEXT_LABEL = "HISTORICAL_MEMORY"
SUMMARY_MESSAGE_THRESHOLD = 10
RECENT_MESSAGE_WINDOW = 8


@dataclass
class ChatTurnResult:
    user_message: Message
    assistant_message: Message
    recall: dict[str, Any]
    actions: list[dict[str, Any]]


async def build_recall_bundle(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol: str | None,
    query: str,
) -> dict[str, Any]:
    if tenant.workspace_id is None:
        return {"label": RECALL_CONTEXT_LABEL, "items": [], "count": 0}
    sym = (symbol or "EURUSD").upper()
    items = await retrieve_memories_hybrid(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol=sym,
        query=query,
        limit=8,
    )
    return {
        "label": RECALL_CONTEXT_LABEL,
        "symbol": sym,
        "items": items,
        "count": len(items),
    }


async def load_conversation_messages(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    *,
    limit: int = RECENT_MESSAGE_WINDOW,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def maybe_refresh_conversation_summary(
    session: AsyncSession,
    conversation: Conversation,
) -> str | None:
    count = await session.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation.id)
    )
    if count is None or count < SUMMARY_MESSAGE_THRESHOLD:
        return conversation.summary_text
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .limit(count - RECENT_MESSAGE_WINDOW)
    )
    older = list(result.scalars().all())
    if not older:
        return conversation.summary_text
    snippets = [f"{m.role.value}: {m.content[:120]}" for m in older[-6:]]
    summary = " | ".join(snippets)
    conversation.summary_text = summary[:4000]
    conversation.summary_updated_at = utc_now()
    await session.flush()
    return conversation.summary_text


def build_llm_messages(
    *,
    conversation: Conversation,
    recall: dict[str, Any],
    history: list[Message],
    user_content: str,
) -> list[LLMMessage]:
    system_parts = [
        f"You are Leovee chat assistant in {conversation.mode.value} mode.",
        "Use labeled historical memory only as context; do not treat it as live prices.",
    ]
    if conversation.summary_text:
        system_parts.append(f"Conversation summary: {conversation.summary_text}")
    if recall.get("count", 0) > 0:
        system_parts.append(
            f"{RECALL_CONTEXT_LABEL}: {json.dumps(recall['items'], default=str)[:6000]}"
        )
    messages = [LLMMessage(role="system", content="\n".join(system_parts))]
    for msg in history:
        if msg.role in {MessageRole.USER, MessageRole.ASSISTANT}:
            messages.append(LLMMessage(role=msg.role.value, content=msg.content))
    messages.append(LLMMessage(role="user", content=user_content))
    return messages


async def run_chat_turn(
    session: AsyncSession,
    tenant: TenantContext,
    conversation: Conversation,
    *,
    user_content: str,
    llm: LLMProvider,
) -> ChatTurnResult:
    await entitlement_service.check_metric_limit(session, tenant, "chat.send")
    recall = await build_recall_bundle(
        session,
        tenant,
        symbol=conversation.symbol,
        query=user_content,
    )
    await maybe_refresh_conversation_summary(session, conversation)
    history = await load_conversation_messages(session, conversation.id)
    llm_messages = build_llm_messages(
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
    response = await llm.complete(llm_messages)
    user_msg = Message(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=user_content,
        symbol_context=conversation.symbol,
    )
    session.add(user_msg)
    assistant = Message(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=response.content,
        content_json={"recall_count": recall["count"], "actions": actions},
        model=response.model,
        provider=response.provider,
        token_usage_json=response.usage,
    )
    session.add(assistant)
    conversation.last_message_at = utc_now()
    await session.flush()
    await entitlement_service.record_usage(session, tenant, "chat.send")
    return ChatTurnResult(
        user_message=user_msg,
        assistant_message=assistant,
        recall=recall,
        actions=actions,
    )

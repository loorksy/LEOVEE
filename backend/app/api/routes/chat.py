from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.datetime_utils import utc_now
from app.core.errors import ProviderConfigurationError
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.conversation import Conversation, ConversationMode, Message, MessageRole
from app.providers.llm.base import LLMMessage
from app.providers.llm.factory import get_llm_provider

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=255)
    symbol: str | None = None
    mode: ConversationMode = ConversationMode.CHAT


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    stream: bool = False


@router.get("")
async def list_conversations(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    result = await session.execute(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant.tenant_id,
            Conversation.workspace_id == tenant.workspace_id,
            Conversation.user_id == tenant.user_id,
        )
        .order_by(Conversation.updated_at.desc())
    )
    rows = list(result.scalars().all())
    return {
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "symbol": c.symbol,
                "mode": c.mode.value,
            }
            for c in rows
        ]
    }


@router.post("")
async def create_conversation(
    body: ConversationCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    conv = Conversation(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
        title=body.title,
        symbol=body.symbol,
        mode=body.mode,
    )
    session.add(conv)
    await session.flush()
    return {"id": str(conv.id)}


@router.post("/{conversation_id}/messages")
async def post_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    stream: Annotated[bool, Query()] = False,
) -> Any:
    conv = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.tenant_id,
            Conversation.workspace_id == tenant.workspace_id,
            Conversation.user_id == tenant.user_id,
        )
    )
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    user_msg = Message(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=body.content,
    )
    session.add(user_msg)
    await session.flush()

    use_stream = stream or body.stream
    try:
        llm = get_llm_provider()
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if use_stream:

        async def event_stream() -> AsyncIterator[str]:
            response = await llm.complete([LLMMessage(role="user", content=body.content)])
            assistant = Message(
                tenant_id=tenant.tenant_id,
                workspace_id=tenant.workspace_id,
                conversation_id=conv.id,
                role=MessageRole.ASSISTANT,
                content=response.content,
                model=response.model,
                provider=response.provider,
            )
            session.add(assistant)
            conv.last_message_at = utc_now()
            await session.flush()
            payload = {"event": "token", "data": response.content}
            yield f"data: {json.dumps(payload)}\n\n"
            yield 'data: {"event": "done"}\n\n'

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    response = await llm.complete([LLMMessage(role="user", content=body.content)])
    assistant = Message(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=response.content,
        model=response.model,
        provider=response.provider,
    )
    session.add(assistant)
    conv.last_message_at = utc_now()
    await session.flush()
    return {
        "user_message_id": str(user_msg.id),
        "assistant_message_id": str(assistant.id),
        "content": response.content,
    }

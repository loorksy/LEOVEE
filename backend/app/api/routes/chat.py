from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.config import get_settings
from app.core.errors import ProviderConfigurationError
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.conversation import Conversation, ConversationMode
from app.providers.llm.anthropic import AnthropicProvider
from app.providers.llm.factory import get_llm_provider
from app.providers.llm.openai import OpenAIProvider
from app.services import chat_service
from app.services.chat_stream import iter_chat_turn_stream

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=255)
    symbol: str | None = None
    mode: ConversationMode = ConversationMode.CHAT


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    stream: bool = False
    mode: ConversationMode | None = None


def _optional_fallback_provider() -> Any | None:
    """Secondary provider for mid-stream failure recovery when both keys exist."""
    settings = get_settings()
    try:
        primary = get_llm_provider(settings)
    except ProviderConfigurationError:
        return None
    if isinstance(primary, OpenAIProvider) and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key)
    if isinstance(primary, AnthropicProvider) and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key)
    return None


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
                "summary_text": c.summary_text,
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


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
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
    rows = await chat_service.load_conversation_messages(session, conv.id, limit=50)
    return {
        "items": [
            {
                "id": str(m.id),
                "role": m.role.value,
                "content": m.content,
                "content_json": m.content_json,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ],
        "summary_text": conv.summary_text,
    }


@router.post("/{conversation_id}/messages")
async def post_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    request: Request,
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

    if body.mode is not None:
        conv.mode = body.mode

    use_stream = stream or body.stream
    try:
        llm = get_llm_provider()
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if use_stream:
        fallback = _optional_fallback_provider()
        conversation_id_value = conv.id
        if body.mode is not None:
            await session.flush()

        async def event_stream() -> AsyncIterator[str]:
            from app.infrastructure.database import get_session_factory

            factory = get_session_factory()
            if factory is None:
                err = {
                    "event": "error",
                    "code": "database_unconfigured",
                    "message": "DATABASE_URL is not configured",
                    "partial_discarded": True,
                }
                yield f"data: {json.dumps(err)}\n\n"
                return
            async with factory() as stream_session:
                stream_conv = await stream_session.scalar(
                    select(Conversation).where(Conversation.id == conversation_id_value)
                )
                if stream_conv is None:
                    err = {
                        "event": "error",
                        "code": "not_found",
                        "message": "Conversation not found",
                        "partial_discarded": True,
                    }
                    yield f"data: {json.dumps(err)}\n\n"
                    return
                if body.mode is not None:
                    stream_conv.mode = body.mode
                try:
                    async for event in iter_chat_turn_stream(
                        stream_session,
                        tenant,
                        stream_conv,
                        user_content=body.content,
                        llm=llm,
                        fallback_llm=fallback,
                    ):
                        if await request.is_disconnected():
                            await stream_session.rollback()
                            return
                        yield f"data: {json.dumps(event, default=str)}\n\n"
                    await stream_session.commit()
                except Exception as exc:  # noqa: BLE001
                    await stream_session.rollback()
                    err = {
                        "event": "error",
                        "code": type(exc).__name__,
                        "message": str(exc) or "stream_failed",
                        "partial_discarded": True,
                    }
                    yield f"data: {json.dumps(err)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    turn = await chat_service.run_chat_turn(
        session,
        tenant,
        conv,
        user_content=body.content,
        llm=llm,
    )
    return {
        "user_message_id": str(turn.user_message.id),
        "assistant_message_id": str(turn.assistant_message.id),
        "content": turn.assistant_message.content,
        "recall": turn.recall,
        "actions": turn.actions,
        "summary_text": conv.summary_text,
    }

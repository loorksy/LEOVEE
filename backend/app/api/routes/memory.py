from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.memory import MemoryType
from app.services import memory_service

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    content: dict[str, Any] = Field(default_factory=dict)
    memory_type: MemoryType = MemoryType.SEMANTIC


@router.get("")
async def list_memories(
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    items = await memory_service.retrieve_memories_for_symbol(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol=symbol,
    )
    return {"items": items}


@router.post("")
async def create_memory(
    body: MemoryCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    memory = await memory_service.store_memory(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        key=body.key,
        content=body.content,
        memory_type=body.memory_type,
    )
    return {"id": str(memory.id)}

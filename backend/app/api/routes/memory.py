from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.memory import MemoryType
from app.services import memory_service
from app.services.memory_maintenance import run_memory_recompute

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    content: dict[str, Any] = Field(default_factory=dict)
    memory_type: MemoryType = MemoryType.SEMANTIC


class MemoryUpdateRequest(BaseModel):
    content: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_memories(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    symbol: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    if symbol:
        items = await memory_service.retrieve_memories_for_symbol(
            session,
            tenant_id=tenant.tenant_id,
            workspace_id=tenant.workspace_id,
            symbol=symbol,
        )
        return {"items": items}
    rows = await memory_service.list_workspace_memories(session, tenant)
    return {
        "items": [
            {
                "id": str(m.id),
                "key": m.key,
                "type": m.memory_type,
                "content": m.content_json,
                "confidence": float(m.confidence) if m.confidence is not None else None,
                "low_sample": m.low_sample,
            }
            for m in rows
        ]
    }


@router.get("/calibration")
async def get_calibration_curve(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    bins = await memory_service.list_calibration_curve(session, tenant)
    return {"bins": bins}


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


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    memory = await memory_service.get_memory(session, tenant, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    await memory_service.update_memory(session, tenant, memory, content=body.content)
    return {"id": str(memory.id)}


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    deleted = await memory_service.delete_memory(session, tenant, memory_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    stats = await run_memory_recompute(session)
    return {"deleted": True, "recompute": stats}

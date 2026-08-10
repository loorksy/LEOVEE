from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import AgentMemory, MemoryType


async def retrieve_memories_for_symbol(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    symbol: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    key_prefix = f"symbol:{symbol.upper()}"
    result = await session.execute(
        select(AgentMemory)
        .where(
            AgentMemory.tenant_id == tenant_id,
            AgentMemory.workspace_id == workspace_id,
            AgentMemory.key.startswith(key_prefix),
        )
        .order_by(AgentMemory.updated_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    return [
        {
            "id": str(row.id),
            "type": row.memory_type,
            "key": row.key,
            "content": row.content_json,
            "confidence": float(row.confidence) if row.confidence is not None else None,
        }
        for row in rows
    ]


async def store_memory(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    key: str,
    content: dict[str, Any],
    memory_type: MemoryType = MemoryType.SEMANTIC,
) -> AgentMemory:
    memory = AgentMemory(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        memory_type=memory_type,
        key=key,
        content_json=content,
        sample_size=1,
        confidence=content.get("confidence"),
    )
    session.add(memory)
    await session.flush()
    return memory

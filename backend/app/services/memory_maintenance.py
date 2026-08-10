from __future__ import annotations

from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import AgentMemory, MemoryEmbedding


async def run_memory_recompute(session: AsyncSession) -> dict[str, int]:
    """Re-index missing embeddings and purge orphan embedding rows."""
    orphan = cast(
        CursorResult[Any],
        await session.execute(
            delete(MemoryEmbedding).where(
                ~MemoryEmbedding.memory_id.in_(select(AgentMemory.id))
            )
        ),
    )
    from app.services.memory_service import index_memory_embedding

    indexed = 0
    rows = await session.execute(
        select(AgentMemory).where(~AgentMemory.id.in_(select(MemoryEmbedding.memory_id)))
    )
    for mem in rows.scalars().all():
        text = f"{mem.key}:{mem.content_json}"
        await index_memory_embedding(
            session,
            tenant_id=mem.tenant_id,
            workspace_id=mem.workspace_id,
            memory_id=mem.id,
            text=text,
        )
        indexed += 1
    return {
        "orphan_embeddings_removed": int(orphan.rowcount or 0),
        "embeddings_indexed": indexed,
    }

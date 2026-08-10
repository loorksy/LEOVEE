from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.infrastructure.rls import set_rls_session_context
from app.models.learning import CalibrationBin, SymbolProfile
from app.models.memory import AgentMemory, MemoryEmbedding, MemoryType
from app.services.learning.calibration import apply_calibration
from app.services.memory.embedding import embed_text_deterministic, merge_rank_hybrid


async def calibrated_confidence_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    stated: Decimal,
) -> Decimal:
    lower = (stated // Decimal("0.1")) * Decimal("0.1")
    upper = min(lower + Decimal("0.1"), Decimal("1"))
    row = await session.scalar(
        select(CalibrationBin).where(
            CalibrationBin.workspace_id == workspace_id,
            CalibrationBin.bin_lower == lower,
            CalibrationBin.bin_upper == upper,
        )
    )
    if row is None:
        return stated
    return apply_calibration(
        stated,
        predicted_count=row.predicted_count,
        realized_success_count=row.realized_success_count,
    )


async def retrieve_memories_for_symbol(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    symbol: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    settings = get_settings()
    await set_rls_session_context(session, tenant_id=tenant_id, workspace_id=workspace_id)
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
    memories = []
    for row in rows:
        confidence = row.confidence
        if confidence is not None:
            confidence = await calibrated_confidence_for_workspace(
                session,
                workspace_id=workspace_id,
                stated=confidence,
            )
        memories.append(
            {
                "id": str(row.id),
                "type": row.memory_type,
                "key": row.key,
                "content": row.content_json,
                "confidence": float(confidence) if confidence is not None else None,
                "low_sample": row.low_sample or row.sample_size < settings.memory_min_sample,
            }
        )

    profile = await session.scalar(
        select(SymbolProfile)
        .where(
            SymbolProfile.workspace_id == workspace_id,
        )
        .limit(1)
    )
    if profile is not None:
        memories.insert(
            0,
            {
                "id": f"profile:{profile.symbol_id}",
                "type": MemoryType.SEMANTIC.value,
                "key": key_prefix,
                "content": profile.profile_json,
                "confidence": float(profile.confidence) if profile.confidence else None,
                "low_sample": profile.sample_size < settings.memory_min_sample,
            },
        )
    return memories


async def index_memory_embedding(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    memory_id: uuid.UUID,
    text: str,
) -> MemoryEmbedding:
    await set_rls_session_context(session, tenant_id=tenant_id, workspace_id=workspace_id)
    vector = embed_text_deterministic(text)
    row = MemoryEmbedding(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        memory_id=memory_id,
        embedding=vector,
        model="deterministic-v1",
    )
    session.add(row)
    await session.flush()
    return row


async def retrieve_memories_hybrid(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    symbol: str,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    keyword_hits = await retrieve_memories_for_symbol(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        symbol=symbol,
        limit=limit,
    )
    await set_rls_session_context(session, tenant_id=tenant_id, workspace_id=workspace_id)
    vector = embed_text_deterministic(query)
    vector_hits: list[dict[str, object]] = []
    try:
        result = await session.execute(
            select(MemoryEmbedding, AgentMemory)
            .join(AgentMemory, AgentMemory.id == MemoryEmbedding.memory_id)
            .where(
                MemoryEmbedding.tenant_id == tenant_id,
                MemoryEmbedding.workspace_id == workspace_id,
                AgentMemory.key.startswith(f"symbol:{symbol.upper()}"),
            )
            .order_by(MemoryEmbedding.embedding.cosine_distance(vector))
            .limit(limit)
        )
        for _emb, mem in result.all():
            vector_hits.append(
                {
                    "id": str(mem.id),
                    "key": mem.key,
                    "content": mem.content_json,
                    "source": "vector",
                }
            )
    except Exception:
        vector_hits = []
    merged = merge_rank_hybrid(keyword_hits, vector_hits, limit=limit)
    return [dict(item) for item in merged]


async def store_memory(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    key: str,
    content: dict[str, Any],
    memory_type: MemoryType = MemoryType.SEMANTIC,
) -> AgentMemory:
    settings = get_settings()
    await set_rls_session_context(session, tenant_id=tenant_id, workspace_id=workspace_id)
    raw_conf = content.get("confidence")
    stated = Decimal(str(raw_conf)) if raw_conf is not None else None
    calibrated = (
        await calibrated_confidence_for_workspace(session, workspace_id=workspace_id, stated=stated)
        if stated is not None
        else None
    )
    memory = AgentMemory(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        memory_type=memory_type,
        key=key,
        content_json=content,
        sample_size=content.get("sample_size", 1),
        confidence=calibrated,
        low_sample=content.get("sample_size", 1) < settings.memory_min_sample,
    )
    session.add(memory)
    await session.flush()
    return memory


async def list_workspace_memories(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    limit: int = 100,
) -> list[AgentMemory]:
    await set_rls_session_context(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
    )
    result = await session.execute(
        select(AgentMemory)
        .where(
            AgentMemory.tenant_id == tenant.tenant_id,
            AgentMemory.workspace_id == tenant.workspace_id,
        )
        .order_by(AgentMemory.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_memory(
    session: AsyncSession,
    tenant: TenantContext,
    memory_id: uuid.UUID,
) -> AgentMemory | None:
    await set_rls_session_context(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
    )
    row = await session.scalar(
        select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.tenant_id == tenant.tenant_id,
            AgentMemory.workspace_id == tenant.workspace_id,
        )
    )
    return row


async def update_memory(
    session: AsyncSession,
    tenant: TenantContext,
    memory: AgentMemory,
    *,
    content: dict[str, Any],
) -> AgentMemory:
    memory.content_json = content
    await session.flush()
    return memory


async def delete_memory(
    session: AsyncSession,
    tenant: TenantContext,
    memory_id: uuid.UUID,
) -> bool:
    memory = await get_memory(session, tenant, memory_id)
    if memory is None:
        return False
    from sqlalchemy import delete

    await session.execute(delete(MemoryEmbedding).where(MemoryEmbedding.memory_id == memory_id))
    await session.delete(memory)
    await session.flush()
    return True


async def list_calibration_curve(
    session: AsyncSession,
    tenant: TenantContext,
) -> list[dict[str, Any]]:
    await set_rls_session_context(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
    )
    result = await session.execute(
        select(CalibrationBin).where(CalibrationBin.workspace_id == tenant.workspace_id)
    )
    bins = list(result.scalars().all())
    return [
        {
            "bin_lower": float(b.bin_lower),
            "bin_upper": float(b.bin_upper),
            "predicted_count": b.predicted_count,
            "realized_success_count": b.realized_success_count,
        }
        for b in bins
    ]

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.learning import CalibrationBin, SymbolProfile
from app.models.memory import AgentMemory, MemoryType
from app.services.learning.calibration import apply_calibration


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

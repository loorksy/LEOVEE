from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.infrastructure.rls import set_rls_session_context
from app.models.memory import AgentEpisode, AgentMemory, Lesson


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def recall_at_time(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol: str,
    as_of: datetime,
    limit: int = 12,
) -> dict[str, Any]:
    """§101 temporal isolation for replay recall."""
    cutoff = _as_utc(as_of)
    await set_rls_session_context(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
    )
    sym = symbol.upper()
    mem_result = await session.execute(
        select(AgentMemory)
        .where(
            AgentMemory.tenant_id == tenant.tenant_id,
            AgentMemory.workspace_id == tenant.workspace_id,
            AgentMemory.key.startswith(f"symbol:{sym}"),
            AgentMemory.created_at <= cutoff,
        )
        .order_by(AgentMemory.created_at.desc())
        .limit(limit)
    )
    memories = [
        {
            "id": str(row.id),
            "key": row.key,
            "content": row.content_json,
            "created_at": row.created_at.isoformat(),
        }
        for row in mem_result.scalars().all()
    ]

    lesson_result = await session.execute(
        select(Lesson)
        .where(
            Lesson.tenant_id == tenant.tenant_id,
            Lesson.workspace_id == tenant.workspace_id,
            Lesson.created_at <= cutoff,
        )
        .order_by(Lesson.created_at.desc())
        .limit(limit)
    )
    lessons = [
        {
            "id": str(row.id),
            "statement": row.statement,
            "created_at": row.created_at.isoformat(),
        }
        for row in lesson_result.scalars().all()
    ]

    episode_result = await session.execute(
        select(AgentEpisode)
        .where(
            AgentEpisode.tenant_id == tenant.tenant_id,
            AgentEpisode.workspace_id == tenant.workspace_id,
            AgentEpisode.occurred_at <= cutoff,
        )
        .order_by(AgentEpisode.occurred_at.desc())
        .limit(limit)
    )
    episodes = [
        {
            "id": str(row.id),
            "outcome": row.outcome,
            "occurred_at": row.occurred_at.isoformat(),
        }
        for row in episode_result.scalars().all()
    ]

    return {
        "as_of": cutoff.isoformat(),
        "memories": memories,
        "lessons": lessons,
        "episodes": episodes,
        "counts": {
            "memories": len(memories),
            "lessons": len(lessons),
            "episodes": len(episodes),
        },
    }

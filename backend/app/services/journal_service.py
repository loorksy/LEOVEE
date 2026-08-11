from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.journal import JournalEntry
from app.models.memory import Lesson


async def list_entries(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    limit: int = 50,
) -> list[JournalEntry]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        select(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant.tenant_id,
            JournalEntry.workspace_id == tenant.workspace_id,
            JournalEntry.user_id == tenant.user_id,
        )
        .order_by(JournalEntry.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_entry(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    title: str,
    notes: str,
    tags: list[str] | None = None,
    emotion: str | None = None,
) -> JournalEntry:
    await bind_workspace_rls(session, tenant)
    entry = JournalEntry(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
        title=title,
        notes=notes,
        tags_json=tags or [],
        emotion=emotion,
    )
    session.add(entry)
    await session.flush()
    return entry


async def promote_to_lesson(
    session: AsyncSession,
    tenant: TenantContext,
    entry: JournalEntry,
) -> Lesson:
    await bind_workspace_rls(session, tenant)
    lesson_text = entry.lesson or entry.notes
    from datetime import timedelta

    from app.core.config import get_settings
    from app.core.datetime_utils import utc_now

    settings = get_settings()
    lesson = Lesson(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        statement=lesson_text,
        conditions_json={"tags": entry.tags_json, "source": "journal", "title": entry.title},
        decay_at=utc_now() + timedelta(days=settings.memory_lesson_ttl_days),
        confidence=1.0,
    )
    session.add(lesson)
    await session.flush()
    entry.promoted_to_lesson_id = lesson.id
    await session.flush()
    return lesson


def entry_to_dict(entry: JournalEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "title": entry.title,
        "notes": entry.notes,
        "tags": entry.tags_json,
        "emotion": entry.emotion,
        "lesson": entry.lesson,
        "promoted_to_lesson_id": (
            str(entry.promoted_to_lesson_id) if entry.promoted_to_lesson_id else None
        ),
        "created_at": entry.created_at.isoformat(),
    }

"""Nightly memory aging sweeps (MEMORY_ARCHITECTURE.md §6.1)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.datetime_utils import utc_now
from app.models.memory import AgentMemory, Lesson


async def run_memory_decay(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
) -> dict[str, int]:
    """Reduce freshness scores and archive expired / stale lessons.

    Raises RuntimeError if the sweep cannot run (no silent success).
    """
    cfg = settings or get_settings()
    now = utc_now()
    factor = Decimal(str(cfg.memory_freshness_decay_factor))
    archive_threshold = Decimal(str(cfg.memory_archive_freshness_threshold))

    if factor <= 0 or factor > 1:
        raise RuntimeError("MEMORY_FRESHNESS_DECAY_FACTOR must be in (0, 1]")
    if archive_threshold < 0 or archive_threshold > 1:
        raise RuntimeError("MEMORY_ARCHIVE_FRESHNESS_THRESHOLD must be in [0, 1]")

    memories_decayed = 0
    mem_rows = await session.execute(
        select(AgentMemory).where((AgentMemory.valid_to.is_(None)) | (AgentMemory.valid_to > now))
    )
    for mem in mem_rows.scalars().all():
        current = mem.freshness_score if mem.freshness_score is not None else Decimal("1.0")
        mem.freshness_score = (current * factor).quantize(Decimal("0.0001"))
        mem.updated_at = now
        memories_decayed += 1

    lessons_archived = 0
    lessons_decayed = 0
    lesson_rows = await session.execute(select(Lesson).where(Lesson.archived_at.is_(None)))
    for lesson in lesson_rows.scalars().all():
        # Confidence doubles as freshness when no dedicated score exists on Lesson.
        current = lesson.confidence if lesson.confidence is not None else Decimal("1.0")
        new_score = (current * factor).quantize(Decimal("0.0001"))
        lesson.confidence = new_score
        lessons_decayed += 1

        past_decay = lesson.decay_at is not None and lesson.decay_at <= now
        below_threshold = new_score < archive_threshold
        if past_decay or below_threshold:
            lesson.archived_at = now
            lessons_archived += 1

    await session.flush()
    return {
        "memories_decayed": memories_decayed,
        "lessons_decayed": lessons_decayed,
        "lessons_archived": lessons_archived,
    }

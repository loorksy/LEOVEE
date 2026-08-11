from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utc_now
from app.models.memory import Lesson
from app.services.learning.outcome_recorder import TerminalOutcome


class LessonProposal(BaseModel):
    statement: str = Field(min_length=8, max_length=2000)
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_episode_ids: list[str] = Field(default_factory=list)


async def propose_lessons_from_outcome(
    session: AsyncSession,
    terminal: TerminalOutcome,
    proposals: list[LessonProposal],
) -> list[Lesson]:
    settings = get_settings()
    saved: list[Lesson] = []
    for proposal in proposals:
        low_sample = len(proposal.supporting_episode_ids) < settings.memory_min_sample
        lesson = Lesson(
            tenant_id=terminal.tenant_id,
            workspace_id=terminal.workspace_id,
            statement=proposal.statement,
            conditions_json=proposal.conditions_json,
            confidence=proposal.confidence,
            supporting_episode_ids=proposal.supporting_episode_ids,
            decay_at=utc_now() + timedelta(days=settings.memory_lesson_ttl_days),
        )
        if low_sample:
            lesson.conditions_json = {
                **lesson.conditions_json,
                "LOW_SAMPLE": True,
            }
        session.add(lesson)
        saved.append(lesson)
    await session.flush()
    return saved

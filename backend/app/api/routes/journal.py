from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.journal import JournalEntry
from app.services import journal_service

router = APIRouter(prefix="/api/v1/journal", tags=["journal"])


class JournalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    notes: str = Field(default="", max_length=32000)
    tags: list[str] = Field(default_factory=list)
    emotion: str | None = None
    lesson: str | None = None


@router.get("")
async def list_journal(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    rows = await journal_service.list_entries(session, tenant)
    return {"items": [journal_service.entry_to_dict(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    body: JournalCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    entry = await journal_service.create_entry(
        session,
        tenant,
        title=body.title,
        notes=body.notes,
        tags=body.tags,
        emotion=body.emotion,
    )
    if body.lesson:
        entry.lesson = body.lesson
    await session.commit()
    return {"id": str(entry.id)}


@router.post("/{entry_id}/promote")
async def promote_journal_entry(
    entry_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    entry = await session.scalar(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.tenant_id == tenant.tenant_id,
            JournalEntry.workspace_id == tenant.workspace_id,
            JournalEntry.user_id == tenant.user_id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    lesson = await journal_service.promote_to_lesson(session, tenant, entry)
    await session.commit()
    return {"lesson_id": str(lesson.id)}

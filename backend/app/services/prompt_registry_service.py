"""Persist which prompt a run was given.

The registry on disk is the source of truth for prompt *text*; this records the
texts that have actually been sent, so a run recorded months ago can still be
traced to the exact words that produced it — after the file has been edited, or
deleted, or renamed.

Idempotent by content hash. The same prompt across a thousand runs is one row,
because the hash is the identity: two deploys shipping identical text are the
same prompt version whatever the file was called in between.

Idempotent **under concurrency**, which a select-then-insert is not. Two
analyses starting together after a prompt edit both see no row under READ
COMMITTED, both insert, and the second raises on the unique index — killing an
analysis that had already completed, over a bookkeeping row. The insert declares
the conflict instead.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import Prompt
from app.models.prompt import PromptVersion

__all__ = ["record_prompt_version"]


async def record_prompt_version(session: AsyncSession, prompt: Prompt) -> PromptVersion:
    existing = await session.scalar(select(PromptVersion).where(PromptVersion.hash == prompt.hash))
    if existing is not None:
        return existing
    await session.execute(
        insert(PromptVersion)
        .values(
            id=uuid.uuid4(),
            hash=prompt.hash,
            name=prompt.name,
            version=prompt.version,
            body=prompt.body,
            metadata_json=dict(prompt.metadata),
        )
        # Whoever wrote it first wins; the row is identical either way, because
        # the hash *is* the content.
        .on_conflict_do_nothing(index_elements=["hash"])
    )
    row = await session.scalar(select(PromptVersion).where(PromptVersion.hash == prompt.hash))
    assert row is not None
    return row

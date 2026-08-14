from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.datetime_utils import utc_now
from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.memory import Lesson, MemoryType
from app.services.memory_decay import run_memory_decay
from app.services.memory_service import store_memory
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_memory_decay_reduces_freshness_and_archives_expired(
    db_session: AsyncSession,
) -> None:
    user, org, _ = await seed_user_org(db_session, email="decay@example.com", slug="decay-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)

    mem = await store_memory(
        db_session,
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        key="symbol:XAUUSD",
        content={"note": "x"},
        memory_type=MemoryType.SEMANTIC,
    )
    mem.freshness_score = Decimal("1.0000")
    now = utc_now()
    expired = Lesson(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        statement="Expired lesson statement long enough",
        conditions_json={},
        confidence=Decimal("0.8000"),
        decay_at=now - timedelta(days=1),
    )
    fresh = Lesson(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        statement="Fresh lesson statement long enough",
        conditions_json={},
        confidence=Decimal("0.9000"),
        decay_at=now + timedelta(days=30),
    )
    db_session.add_all([expired, fresh])
    await db_session.flush()

    settings = Settings(
        MEMORY_FRESHNESS_DECAY_FACTOR=0.5,
        MEMORY_ARCHIVE_FRESHNESS_THRESHOLD=0.15,
    )
    stats = await run_memory_decay(db_session, settings=settings)
    await db_session.flush()

    assert stats["memories_decayed"] >= 1
    assert stats["lessons_archived"] >= 1
    await db_session.refresh(mem)
    await db_session.refresh(expired)
    await db_session.refresh(fresh)
    assert mem.freshness_score == Decimal("0.5000")
    assert expired.archived_at is not None
    assert fresh.archived_at is None
    assert fresh.confidence == Decimal("0.4500")


@pytest.mark.asyncio
async def test_memory_decay_rejects_invalid_factor() -> None:
    settings = Settings(MEMORY_FRESHNESS_DECAY_FACTOR=0.0)
    with pytest.raises(RuntimeError, match="DECAY_FACTOR"):
        await run_memory_decay(MagicMock(), settings=settings)

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationDirection, RecommendationStatus, ThesisStatus
from app.models.recommendation import Thesis
from app.models.thesis_event import ThesisEvent
from app.services import market_data, recommendation_service
from app.services.thesis_monitor_service import monitor_thesis_row
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_thesis_monitor_invalidates_on_structure_break(db_session: AsyncSession) -> None:
    user, _org, _m = await seed_user_org(db_session)
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)

    await market_data.get_or_create_symbol(db_session, "XAUUSD")
    rec = await recommendation_service.create_recommendation(
        db_session,
        ctx,
        symbol_code="XAUUSD",
        direction=RecommendationDirection.BUY,
        status=RecommendationStatus.ACTIVE,
        evidence={"engines": {"structure": {"swing_low": 1.095}}},
    )
    thesis = await recommendation_service.spawn_thesis_from_recommendation(
        db_session,
        ctx,
        rec,
        statement="Bullish XAUUSD",
    )
    thesis.invalidation_json = {"swing_low": 1.0950}
    await db_session.flush()

    await monitor_thesis_row(
        db_session,
        ctx,
        thesis,
        rec,
        last_price=Decimal("1.0900"),
        structure={"swing_low": 1.0950, "swing_high": 1.1200},
    )
    await db_session.commit()

    await bind_workspace_rls(db_session, ctx)
    updated = await db_session.scalar(select(Thesis).where(Thesis.id == thesis.id))
    assert updated is not None
    assert updated.status == ThesisStatus.INVALIDATED

    events = await db_session.execute(select(ThesisEvent).where(ThesisEvent.thesis_id == thesis.id))
    assert len(events.scalars().all()) >= 1

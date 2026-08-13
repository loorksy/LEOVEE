from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.models.notification import Notification
from app.services import alert_service, market_data
from app.services.alert_evaluation import run_alert_evaluation_cycle
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_alert_evaluation_cycle_fans_out_notification(
    db_session: AsyncSession,
) -> None:
    user, org, _ = await seed_user_org(
        db_session, email="alert-eval@example.com", slug="alert-eval"
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    await bind_workspace_rls(db_session, ctx)
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    db_session.add(
        Candle(
            symbol_id=symbol.id,
            timeframe=Timeframe.H1,
            ts=datetime(2026, 1, 1, 12, tzinfo=UTC),
            open=Decimal("1.1000"),
            high=Decimal("1.1100"),
            low=Decimal("1.0900"),
            close=Decimal("1.1050"),
            volume=Decimal("0"),
            complete=True,
            source="test",
        )
    )
    alert = await alert_service.create_alert(
        db_session,
        ctx,
        alert_type="PRICE",
        symbol_code="XAUUSD",
        condition={"op": "gte", "price": 1.10},
        channels={"in_app": True},
    )
    await db_session.flush()

    stats = await run_alert_evaluation_cycle(db_session)
    await db_session.flush()

    assert stats["alerts_evaluated"] >= 1
    assert stats["alerts_triggered"] >= 1
    await db_session.refresh(alert)
    assert alert.last_triggered_at is not None
    notes = await db_session.execute(
        select(Notification).where(Notification.resource_id == alert.id)
    )
    assert len(notes.scalars().all()) >= 1

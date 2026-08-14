from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationDirection
from app.services import trade_service
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_trade_execution_gate_blocks_live_orders(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session)
    ctx = await resolve_tenant_context(db_session, user.id)
    await bind_workspace_rls(db_session, ctx)
    with pytest.raises(ValueError, match="execution_disabled_by_policy"):
        await trade_service.create_trade_idea(
            db_session,
            ctx,
            symbol_code="XAUUSD",
            direction=RecommendationDirection.BUY,
            execution_enabled=True,
        )

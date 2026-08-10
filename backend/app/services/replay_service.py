from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.engines.replay.historical_replay_engine import HistoricalReplayEngine, ReplaySlice
from app.models.enums import Timeframe
from app.services import entitlement_service


class ReplayNotEnabledError(entitlement_service.EntitlementError):
    pass


async def assert_replay_enabled(session: AsyncSession, tenant: TenantContext) -> None:
    plan, _sub = await entitlement_service.get_active_plan(session, tenant.tenant_id)
    features = plan.features_json or {}
    if features.get("replay_enabled") is False:
        raise ReplayNotEnabledError(
            "feature_disabled",
            "Historical replay is not enabled on this plan",
        )


async def preview_replay(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol: str,
    timeframe: Timeframe,
    as_of: datetime,
) -> dict[str, Any]:
    await assert_replay_enabled(session, tenant)
    engine = HistoricalReplayEngine()
    return await engine.build_preview(
        session,
        tenant,
        ReplaySlice(symbol=symbol.upper(), timeframe=timeframe, as_of=as_of),
    )

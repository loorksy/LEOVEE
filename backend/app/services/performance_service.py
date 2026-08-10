from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.enums import RecommendationStatus
from app.models.recommendation import Recommendation
from app.models.trade import Trade


async def workspace_performance_summary(
    session: AsyncSession,
    tenant: TenantContext,
) -> dict[str, Any]:
    rec_counts = await session.execute(
        select(Recommendation.status, func.count())
        .where(
            Recommendation.tenant_id == tenant.tenant_id,
            Recommendation.workspace_id == tenant.workspace_id,
        )
        .group_by(Recommendation.status)
    )
    status_map = {row[0].value: int(row[1]) for row in rec_counts.all()}

    trade_count = await session.scalar(
        select(func.count())
        .select_from(Trade)
        .where(
            Trade.tenant_id == tenant.tenant_id,
            Trade.workspace_id == tenant.workspace_id,
        )
    )

    ready = status_map.get(RecommendationStatus.READY.value, 0)
    active = status_map.get(RecommendationStatus.ACTIVE.value, 0)
    invalidated = status_map.get(RecommendationStatus.INVALIDATED.value, 0)
    total_recs = sum(status_map.values())
    win_proxy = ready + active
    calibration = (win_proxy / total_recs) if total_recs else 0.0

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "recommendations": status_map,
        "trade_ideas": int(trade_count or 0),
        "calibration_proxy": round(calibration, 4),
        "invalidated_rate": round(invalidated / total_recs, 4) if total_recs else 0.0,
    }

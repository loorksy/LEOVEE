from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationStatus
from app.models.learning import CalibrationBin, OutcomeRecord
from app.models.recommendation import Recommendation
from app.models.trade import Trade
from app.services import memory_service


async def workspace_performance_summary(
    session: AsyncSession,
    tenant: TenantContext,
) -> dict[str, Any]:
    await bind_workspace_rls(session, tenant)
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

    outcome_count = await session.scalar(
        select(func.count())
        .select_from(OutcomeRecord)
        .where(
            OutcomeRecord.tenant_id == tenant.tenant_id,
            OutcomeRecord.workspace_id == tenant.workspace_id,
        )
    )

    bins = await memory_service.list_calibration_curve(session, tenant)
    predicted_total = sum(b["predicted_count"] for b in bins)
    realized_total = sum(b["realized_success_count"] for b in bins)
    calibration_rate = (realized_total / predicted_total) if predicted_total else 0.0

    total_recs = sum(status_map.values())
    terminal = (
        status_map.get(RecommendationStatus.TARGET_REACHED.value, 0)
        + status_map.get(RecommendationStatus.INVALIDATED.value, 0)
        + status_map.get(RecommendationStatus.EXPIRED.value, 0)
    )

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "recommendations": status_map,
        "trade_ideas": int(trade_count or 0),
        "outcome_records": int(outcome_count or 0),
        "terminal_recommendations": terminal,
        "calibration": {
            "bins": bins,
            "predicted_total": predicted_total,
            "realized_success_total": realized_total,
            "rate": round(calibration_rate, 6),
        },
        "invalidated_rate": round(
            status_map.get(RecommendationStatus.INVALIDATED.value, 0) / total_recs,
            6,
        )
        if total_recs
        else 0.0,
    }


async def aggregate_check(
    session: AsyncSession,
    tenant: TenantContext,
) -> dict[str, int]:
    """Direct DB aggregates for §99 parity tests."""
    await bind_workspace_rls(session, tenant)
    rec_total = await session.scalar(
        select(func.count())
        .select_from(Recommendation)
        .where(
            Recommendation.tenant_id == tenant.tenant_id,
            Recommendation.workspace_id == tenant.workspace_id,
        )
    )
    bin_rows = await session.execute(
        select(
            func.coalesce(func.sum(CalibrationBin.predicted_count), 0),
            func.coalesce(func.sum(CalibrationBin.realized_success_count), 0),
        ).where(CalibrationBin.workspace_id == tenant.workspace_id)
    )
    predicted, realized = bin_rows.one()
    return {
        "recommendation_count": int(rec_total or 0),
        "calibration_predicted_sum": int(predicted or 0),
        "calibration_realized_sum": int(realized or 0),
    }

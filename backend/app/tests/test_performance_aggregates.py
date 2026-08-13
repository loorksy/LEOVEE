from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.learning import CalibrationBin
from app.services import performance_service, recommendation_service
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_performance_summary_matches_db_aggregates(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="perf@example.com", slug="perf-org")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)

    await recommendation_service.create_recommendation(
        db_session,
        ctx,
        symbol_code="XAUUSD",
        direction=RecommendationDirection.BUY,
        status=RecommendationStatus.READY,
    )
    db_session.add(
        CalibrationBin(
            tenant_id=org.id,
            workspace_id=ctx.workspace_id,
            bin_lower=0.5,
            bin_upper=0.6,
            predicted_count=10,
            realized_success_count=6,
        )
    )
    await db_session.flush()

    direct = await performance_service.aggregate_check(db_session, ctx)
    summary = await performance_service.workspace_performance_summary(db_session, ctx)

    assert summary["recommendations"]["READY"] == 1
    assert direct["recommendation_count"] == 1
    assert summary["calibration"]["predicted_total"] == direct["calibration_predicted_sum"]
    assert summary["calibration"]["realized_success_total"] == direct["calibration_realized_sum"]

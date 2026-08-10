from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.enums import RecommendationDirection, RecommendationStatus, Timeframe
from app.providers.market.base import MarketDataProvider
from app.services import recommendation_service
from app.services.analysis_service import map_decision_to_recommendation_status, run_analysis
from app.services.reasoning_baseline import run_reasoning_baseline


async def run_analysis_pipeline(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol: str,
    timeframe: Timeframe = Timeframe.H1,
    market_provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    """
    Baseline §99 path: market → analysis → reasoning → recommendation → thesis.
    """
    analysis = await run_analysis(
        session,
        tenant,
        symbol=symbol,
        timeframe=timeframe,
        persist_engines=True,
        market_provider=market_provider,
    )

    reasoning = run_reasoning_baseline(
        symbol=symbol,
        decision=analysis["decision"],
        engines=analysis["engines"],
    )

    direction_value = analysis["decision"].get("direction", RecommendationDirection.WAIT.value)
    try:
        direction = RecommendationDirection(direction_value)
    except ValueError:
        direction = RecommendationDirection.WAIT

    status = map_decision_to_recommendation_status(analysis["decision"])
    if not reasoning.get("approved"):
        status = RecommendationStatus.FORMING

    agent_run_id = uuid.UUID(analysis["agent_run_id"])
    rec = await recommendation_service.create_recommendation(
        session,
        tenant,
        symbol_code=symbol,
        direction=direction,
        status=status,
        evidence={
            "reasoning": reasoning,
            "decision": analysis["decision"],
            "engines": analysis["engines"],
            "persistence": analysis.get("persistence"),
        },
        agent_run_id=agent_run_id,
    )
    thesis = await recommendation_service.spawn_thesis_from_recommendation(
        session,
        tenant,
        rec,
        statement=str(reasoning.get("summary")),
    )

    return {
        **analysis,
        "reasoning": reasoning,
        "recommendation_id": str(rec.id),
        "thesis_id": str(thesis.id),
    }

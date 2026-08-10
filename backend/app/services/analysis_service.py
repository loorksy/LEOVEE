from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_analysis_orchestrator
from app.core.tenant import TenantContext
from app.models.enums import RecommendationDirection, RecommendationStatus, Timeframe
from app.services import market_data
from app.services.memory_service import retrieve_memories_for_symbol


async def run_analysis(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol: str,
    timeframe: Timeframe = Timeframe.H1,
) -> dict[str, Any]:
    _symbol, candles = await market_data.fetch_and_store_candles(
        session,
        symbol_code=symbol,
        timeframe=timeframe,
    )
    memories = await retrieve_memories_for_symbol(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol=symbol,
    )
    result = await run_analysis_orchestrator(
        symbol=symbol,
        candles=candles,
        memories=memories,
    )
    return {
        "agent_run_id": str(result.agent_run_id),
        "workspace_id": str(tenant.workspace_id),
        "symbol": symbol,
        "timeframe": timeframe.value,
        "perceive": result.perceive,
        "recall": result.recall,
        "engines": result.engines,
        "decision": result.decision,
        "narrative": result.narrative,
    }


def map_decision_to_recommendation_status(decision: dict[str, Any]) -> RecommendationStatus:
    direction = decision.get("direction")
    if direction == RecommendationDirection.NO_TRADE.value:
        return RecommendationStatus.INVALIDATED
    if decision.get("confidence", 0) >= 0.5:
        return RecommendationStatus.READY
    return RecommendationStatus.FORMING

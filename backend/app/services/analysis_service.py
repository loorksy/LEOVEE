from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_analysis_orchestrator
from app.core.tenant import TenantContext
from app.engines.reasoning import run_devils_advocate, run_reasoning_engine
from app.models.enums import RecommendationDirection, RecommendationStatus, Timeframe
from app.providers.market.base import MarketDataProvider
from app.services import entitlement_service, market_data, recommendation_service
from app.services.market.engine_persistence import persist_engine_outputs
from app.services.market_intelligence_service import build_mtf_intelligence
from app.services.memory_service import retrieve_memories_for_symbol


def map_decision_to_recommendation_status(decision: dict[str, Any]) -> RecommendationStatus:
    direction = decision.get("direction")
    if direction == RecommendationDirection.NO_TRADE.value:
        return RecommendationStatus.INVALIDATED
    if decision.get("confidence", 0) >= 0.5:
        return RecommendationStatus.READY
    return RecommendationStatus.FORMING


async def run_analysis(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol: str,
    timeframe: Timeframe = Timeframe.H1,
    persist_engines: bool = True,
    market_provider: MarketDataProvider | None = None,
    complete_pipeline: bool = False,
) -> dict[str, Any]:
    await entitlement_service.check_metric_limit(session, tenant, "analysis.run")
    symbol_row, candles = await market_data.fetch_and_store_candles(
        session,
        symbol_code=symbol,
        timeframe=timeframe,
        provider=market_provider,
    )
    memories = await retrieve_memories_for_symbol(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol=symbol,
    )
    mtf_snapshot = await build_mtf_intelligence(
        session,
        symbol=symbol,
        provider=market_provider,
    )
    result = await run_analysis_orchestrator(
        symbol=symbol,
        candles=candles,
        memories=memories,
        mtf_context=mtf_snapshot,
    )
    payload: dict[str, Any] = {
        "agent_run_id": str(result.agent_run_id),
        "workspace_id": str(tenant.workspace_id),
        "symbol": symbol,
        "timeframe": timeframe.value,
        "perceive": result.perceive,
        "recall": result.recall,
        "engines": result.engines,
        "decision": result.decision,
        "narrative": result.narrative,
        "as_of": candles[-1].ts.isoformat(),
    }
    if persist_engines:
        counts = await persist_engine_outputs(
            session,
            symbol_id=symbol_row.id,
            timeframe=timeframe.value,
            as_of=candles[-1].ts,
            engines=result.engines,
        )
        payload["persistence"] = counts

    if complete_pipeline:
        adversarial = run_devils_advocate(decision=result.decision, engines=result.engines)
        reasoning = run_reasoning_engine(
            symbol=symbol,
            decision=result.decision,
            engines=result.engines,
            adversarial=adversarial,
        )
        direction_value = result.decision.get("direction", RecommendationDirection.WAIT.value)
        try:
            direction = RecommendationDirection(direction_value)
        except ValueError:
            direction = RecommendationDirection.WAIT
        status = RecommendationStatus(reasoning["status"])
        rec = await recommendation_service.create_recommendation(
            session,
            tenant,
            symbol_code=symbol,
            direction=direction,
            status=status,
            evidence={
                "reasoning": reasoning,
                "decision": result.decision,
                "engines": result.engines,
                "persistence": payload.get("persistence"),
            },
            agent_run_id=result.agent_run_id,
        )
        thesis = await recommendation_service.spawn_thesis_from_recommendation(
            session,
            tenant,
            rec,
            statement=str(reasoning.get("summary")),
        )
        payload["reasoning"] = reasoning
        payload["recommendation_id"] = str(rec.id)
        payload["thesis_id"] = str(thesis.id)

    await entitlement_service.record_usage(session, tenant, "analysis.run")
    return payload

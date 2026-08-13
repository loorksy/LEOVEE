from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import fail_closed_no_trade, run_analysis_orchestrator
from app.core.tenant import TenantContext
from app.engines.reasoning import run_devils_advocate, run_reasoning_engine
from app.models.enums import RecommendationDirection, RecommendationStatus, Timeframe
from app.models.memory import MemoryType
from app.providers.market.base import MarketDataProvider
from app.services import entitlement_service, market_data, recommendation_service
from app.services.market.engine_persistence import persist_engine_outputs
from app.services.market_intelligence_service import build_mtf_intelligence
from app.services.memory_service import retrieve_memories_for_symbol, store_memory


def map_decision_to_recommendation_status(decision: dict[str, Any]) -> RecommendationStatus:
    direction = decision.get("direction")
    if direction == RecommendationDirection.NO_TRADE.value:
        return RecommendationStatus.INVALIDATED
    confidence = decision.get("confidence")
    if confidence is not None and float(confidence) >= 0.5:
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
        try:
            adversarial = run_devils_advocate(decision=result.decision, engines=result.engines)
        except Exception as exc:  # noqa: BLE001 — fail closed when adversarial cannot run
            # Preserve an earlier fail-closed reason (e.g. LLM_UNAVAILABLE).
            if not result.decision.get("degraded"):
                result.decision = fail_closed_no_trade("ADVERSARIAL_UNAVAILABLE", detail=str(exc))
                payload["decision"] = result.decision
                narrative = result.narrative if isinstance(result.narrative, dict) else {}
                payload["narrative"] = {
                    **narrative,
                    "adversarial_unavailable": str(exc),
                    "degraded_reason": "ADVERSARIAL_UNAVAILABLE",
                }
            adversarial = {
                "approved": False,
                "issues": ["ADVERSARIAL_UNAVAILABLE"],
                "severity": "HIGH",
                "error": str(exc),
            }

        reasoning = run_reasoning_engine(
            symbol=symbol,
            decision=result.decision,
            engines=result.engines,
            adversarial=adversarial,
        )
        direction_value = result.decision.get("direction", RecommendationDirection.NO_TRADE.value)
        try:
            direction = RecommendationDirection(direction_value)
        except ValueError:
            direction = RecommendationDirection.NO_TRADE
        # Degraded analysis must never become a directional READY recommendation.
        if result.decision.get("degraded"):
            status = RecommendationStatus.INVALIDATED
            direction = RecommendationDirection.NO_TRADE
        else:
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
        # Persist a symbol-scoped memory so subsequent runs recall prior analysis.
        conf = result.decision.get("confidence")
        memory = await store_memory(
            session,
            tenant_id=tenant.tenant_id,
            workspace_id=tenant.workspace_id,
            key=f"symbol:{symbol.upper()}:analysis:{result.agent_run_id}",
            content={
                "symbol": symbol.upper(),
                "timeframe": timeframe.value,
                "decision": result.decision,
                "recommendation_id": str(rec.id),
                "thesis_id": str(thesis.id),
                "summary": str(reasoning.get("summary") or f"{symbol.upper()} {direction_value}"),
                "confidence": None if conf is None else float(conf),
                "sample_size": 1,
                "agent_run_id": str(result.agent_run_id),
            },
            memory_type=MemoryType.SEMANTIC,
        )
        payload["reasoning"] = reasoning
        payload["recommendation_id"] = str(rec.id)
        payload["thesis_id"] = str(thesis.id)
        payload["memory_id"] = str(memory.id)

    await entitlement_service.record_usage(session, tenant, "analysis.run")
    return payload

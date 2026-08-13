from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import fail_closed_no_trade, run_analysis_orchestrator
from app.agents.prompts import Prompt, PromptNotFound, constitution
from app.agents.tools.registry import ToolContext
from app.core.tenant import TenantContext
from app.engines.reasoning import run_devils_advocate, run_reasoning_engine
from app.models.enums import RecommendationDirection, RecommendationStatus, Timeframe
from app.models.memory import MemoryType
from app.providers.market.base import MarketDataProvider
from app.services import entitlement_service, market_data, recommendation_service
from app.services.agent_run_service import persist_agent_run
from app.services.chart.visual_evidence import collect_visual_evidence
from app.services.market.engine_persistence import persist_engine_outputs
from app.services.market.history import TIMEFRAME_MINUTES
from app.services.market_intelligence_service import build_mtf_intelligence
from app.services.memory_service import retrieve_memories_for_symbol, store_memory


def _plan_columns(decision: dict[str, Any], *, tenant_timeframe: Timeframe) -> dict[str, Any]:
    """The plan's own columns, from a completed decision.

    Empty for a degraded run: a NO_TRADE has no levels, and writing zeros or the
    last price into those columns would give the tracker a stop to watch on a
    plan that was never made.
    """
    if decision.get("degraded") or decision.get("direction") in {
        RecommendationDirection.NO_TRADE.value,
        RecommendationDirection.WAIT.value,
    }:
        return {}

    levels = decision.get("levels") or {}
    plan_type = decision.get("plan_type")
    return {
        "entry": _as_decimal(levels.get("entry")),
        "stop": _as_decimal(levels.get("stop")),
        "targets": [float(t) for t in (levels.get("targets") or [])],
        "timeframe": decision.get("timeframe") or tenant_timeframe.value,
        "plan_type": plan_type,
        "execution_state": decision.get("execution_state"),
        "activation_rule": decision.get("activation_rule"),
        "activation_condition": decision.get("condition"),
        "expires_at": _validity_deadline(decision, tenant_timeframe),
    }


def _as_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _validity_deadline(decision: dict[str, Any], timeframe: Timeframe) -> datetime | None:
    """When the plan stops being worth showing.

    Derived from the frame it was made on, because "twelve candles" is a
    different amount of time on M1 and M15 — and a plan with no deadline is one
    that still reads as live three sessions after the structure that justified
    it stopped existing.
    """
    candles = decision.get("validity_candles")
    if not isinstance(candles, int) or candles <= 0:
        return None
    minutes = TIMEFRAME_MINUTES.get(timeframe)
    if minutes is None:
        return None
    return datetime.now(UTC) + timedelta(minutes=minutes * candles)


def _constitution_or_none() -> Prompt | None:
    """The prompt to catalogue, or nothing if it could not be read.

    Never raises: a prompt-registry problem has already failed the analysis
    upstream, and failing the *write* here would additionally lose the trace
    that explains why.
    """
    try:
        return constitution()
    except PromptNotFound:
        return None


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
    started_at = datetime.now(UTC)
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
    # Charts for the decision stage, drawn from the same candle rows the engines
    # read (never a browser screenshot: two ways of seeing produce two answers).
    # Best-effort by contract — a missing frame is reported, and the analysis
    # proceeds on numbers alone rather than being lost with the pictures.
    visual = await collect_visual_evidence(
        session,
        symbol=symbol,
        timeframe=timeframe,
    )
    result = await run_analysis_orchestrator(
        symbol=symbol,
        candles=candles,
        memories=memories,
        mtf_context=mtf_snapshot,
        # The ladder is already loaded for the MTF read, so the agent's own
        # timeframe choice costs no extra fetch (D11).
        bars_by_timeframe=mtf_snapshot.get("bars_by_timeframe"),
        visual_evidence=[s.as_payload() for s in visual.snapshots],
        # Gives the decision stage the read-only tools: the digest it is sent is
        # deliberately partial, and this is how the elided detail stays
        # reachable instead of being reasoned around.
        tool_context=ToolContext(session=session, symbol=symbol),
    )
    # The run is written before anything downstream can fail: a recommendation
    # that references an agent_run_id has to be able to find it, and a degraded
    # run is exactly the one whose trace is worth keeping.
    await persist_agent_run(
        session,
        tenant,
        result=result,
        symbol=symbol,
        started_at=started_at,
        user_id=tenant.user_id,
        # Catalogue the prompt text alongside the hash, or prompt_hash is a
        # pointer into an empty table and M8 cannot resolve it.
        prompt=_constitution_or_none(),
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
        "pipeline": result.pipeline,
        "visual": {"frames": [s.timeframe for s in visual.snapshots], "missing": visual.missing},
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
            # Only a completed analysis has one. A degraded run reaches here
            # with confidence None and must keep it.
            confidence=(
                None
                if result.decision.get("confidence") is None
                else Decimal(str(result.decision["confidence"]))
            ),
            # The plan itself, not just its direction. Before this, the levels
            # the analysis produced lived only inside evidence_json — so the
            # tracker had no stop to watch and no condition to evaluate, and a
            # recommendation could never resolve on its own.
            **_plan_columns(result.decision, tenant_timeframe=timeframe),
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

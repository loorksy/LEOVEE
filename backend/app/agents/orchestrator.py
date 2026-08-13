"""The analysis pipeline: one visible agent over a fleet of specialists.

The graph, and where each piece lives:

    market_data                          (the caller: candles are already loaded)
      → structure ∥ liquidity ∥ zones ∥ geometry ∥ volatility     app/engines/
      → multi_timeframe                                           app/engines/mtf
      → timeframe_selection                                       app/agents/timeframe
      → scenarios → risk → plan_sanity                            app/engines/
      → final_decision                                            the model layer

AiChart's ``execution_guard`` stage is deleted and ``plan_sanity`` occupies its
position as a deterministic gate (D4).

**The fail-closed contract is the safety valve, and it is stricter than
AiChart's degraded mode.** Any engine that cannot answer stops the run here:
pricing risk and writing a narrative on top of missing evidence produces a
confident, plausible, unfounded recommendation, which is the exact failure the
contract exists to prevent. AiChart's operational messages carry over as
*explanations attached to* NO_TRADE, never as a path around it.

**Evidence is assembled before the decision, always.** Not for tidiness: a
decision stage that runs while evidence is still arriving will use whatever
happens to be ready, and which subset that is varies by provider latency — so
the same market produces different recommendations on different days for
reasons nothing records.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.agents.errors import AgentStage, StageFailure, stage_failure_from_error
from app.agents.pipeline import PipelineLedger
from app.agents.prompts import PromptNotFound, constitution
from app.agents.synthesizer import synthesize_decision
from app.agents.timeframe import (
    NoViableTimeframeError,
    TimeframeChoice,
    select_decision_timeframe,
)
from app.core.errors import ProviderConfigurationError
from app.core.timeframes import INTERIM_DECISION_TIMEFRAME
from app.engines.bar import OHLCBar, bars_from_candles
from app.engines.decision import run_decision_engine
from app.engines.geometry import run_geometry_engine
from app.engines.liquidity import run_liquidity_engine
from app.engines.market_intelligence import run_market_intelligence_engine
from app.engines.mtf import run_mtf_engine
from app.engines.plan_sanity import risk_policy_for, run_plan_sanity_engine
from app.engines.risk import run_risk_engine
from app.engines.scenario import run_scenario_engine
from app.engines.status import unavailable_engines
from app.engines.structure import run_structure_engine
from app.engines.volatility import run_volatility_engine
from app.engines.zones import run_zones_engine
from app.models.enums import RecommendationDirection, Timeframe
from app.providers.llm.base import LLMMessage, LLMProvider
from app.providers.llm.factory import get_llm_provider

__all__ = [
    "OrchestratorResult",
    "bars_from_candles",
    "fail_closed_no_trade",
    "run_analysis_orchestrator",
    "unavailable_engines",
]


@dataclass
class OrchestratorResult:
    agent_run_id: uuid.UUID
    perceive: dict[str, Any] = field(default_factory=dict)
    recall: dict[str, Any] = field(default_factory=dict)
    engines: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    narrative: dict[str, Any] = field(default_factory=dict)
    #: What every stage did, including the ones that failed. Persisted to
    #: agent_traces so a degraded run can be explained after the fact.
    pipeline: dict[str, Any] = field(default_factory=dict)
    #: The prompt this run was given, by content hash.
    prompt_hash: str | None = None
    #: Which model actually answered. Without it a run cannot be attributed to
    #: an LLM after the fact, which is most of what run-level observability is
    #: for when several providers rotate behind one router.
    model: str | None = None
    provider: str | None = None


def fail_closed_no_trade(reason: str, *, detail: str | None = None) -> dict[str, Any]:
    """Spec §95: analysis-path failures resolve to NO_TRADE — never a soft BUY/SELL."""
    payload: dict[str, Any] = {
        "direction": RecommendationDirection.NO_TRADE.value,
        "confidence": None,
        "rationale": reason,
        "degraded": True,
        "degraded_reason": reason,
    }
    if detail:
        payload["detail"] = detail
    return payload


def _choose_timeframe(
    ledger: PipelineLedger,
    bars_by_timeframe: dict[str, list[OHLCBar]],
    *,
    leading_bias: str | None,
    symbol: str,
    moment: datetime | None,
) -> TimeframeChoice | None:
    """Let the agent pick its frame, or record why it could not."""
    try:
        return select_decision_timeframe(
            bars_by_timeframe,
            leading_bias=leading_bias,
            symbol=symbol,
            moment=moment,
        )
    except NoViableTimeframeError as exc:
        ledger.failures.append(
            StageFailure(
                stage=AgentStage.TIMEFRAME_SELECTION,
                code=stage_failure_from_error(AgentStage.TIMEFRAME_SELECTION, exc).code,
                retryable=False,
                operator_detail=str(exc)[:500],
            )
        )
        return None


async def run_analysis_orchestrator(
    *,
    symbol: str,
    candles: list[Any],
    memories: list[dict[str, Any]] | None = None,
    llm: LLMProvider | None = None,
    mtf_context: dict[str, Any] | None = None,
    bars_by_timeframe: dict[str, list[OHLCBar]] | None = None,
    visual_evidence: list[dict[str, Any]] | None = None,
) -> OrchestratorResult:
    if not candles:
        raise ValueError("Analysis requires at least one stored candle")

    run_id = uuid.uuid4()
    ledger = PipelineLedger()
    perceive = {"symbol": symbol, "candle_count": len(candles)}
    recall = {"memories": memories or [], "count": len(memories or [])}

    bars = bars_from_candles(candles)
    # The moment the candles belong to, not the wall clock: the cost floor is
    # session-shaped, so reading `now()` would make an identical replay of this
    # analysis reach a different answer.
    as_of = bars[-1].ts

    volatility = run_volatility_engine(bars)
    structure = run_structure_engine(bars)
    geometry = run_geometry_engine(bars)
    liquidity = run_liquidity_engine(bars)
    zones = run_zones_engine(bars)
    intelligence = run_market_intelligence_engine(bars)

    if mtf_context and "mtf" in mtf_context:
        mtf = mtf_context["mtf"]
        intelligence_by_tf = mtf_context.get("intelligence_by_tf", {})
    else:
        intelligence_by_tf = {INTERIM_DECISION_TIMEFRAME.value: intelligence}
        mtf = run_mtf_engine({INTERIM_DECISION_TIMEFRAME.value: bars})

    # The agent picks its own frame (D11). Falls back to the frame the caller
    # analysed only when the ladder was never loaded — with the fallback
    # recorded, not hidden.
    frames = bars_by_timeframe or {INTERIM_DECISION_TIMEFRAME.value: bars}
    leading_bias = mtf.get("trade_bias") if isinstance(mtf, dict) else None
    choice = _choose_timeframe(
        ledger, frames, leading_bias=leading_bias, symbol=symbol, moment=as_of
    )
    decision_timeframe: Timeframe = choice.timeframe if choice else INTERIM_DECISION_TIMEFRAME

    scenarios = run_scenario_engine(structure, volatility, liquidity, zones, mtf)

    evidence = {
        "volatility": volatility,
        "structure": structure,
        "geometry": geometry,
        "liquidity": liquidity,
        "zones": zones,
        "scenarios": scenarios,
        "market_intelligence": intelligence,
        "mtf": mtf,
    }

    missing = unavailable_engines(evidence)
    if missing:
        return OrchestratorResult(
            agent_run_id=run_id,
            perceive=perceive,
            recall=recall,
            engines={**evidence, "intelligence_by_tf": intelligence_by_tf},
            decision=fail_closed_no_trade("ENGINE_UNAVAILABLE", detail=", ".join(missing)),
            narrative={
                "degraded_reason": "ENGINE_UNAVAILABLE",
                "unavailable_engines": missing,
            },
            pipeline=ledger.to_dict(),
        )

    if choice is None:
        # Every scalping frame was excluded — unreadable, too thin, or unable to
        # clear its own costs. That is an answer, and a more useful one than a
        # plan on a chart the agent has just established it cannot trade.
        return OrchestratorResult(
            agent_run_id=run_id,
            perceive=perceive,
            recall=recall,
            engines={**evidence, "intelligence_by_tf": intelligence_by_tf},
            decision=fail_closed_no_trade(
                "NO_VIABLE_TIMEFRAME",
                detail=ledger.failures[-1].operator_detail if ledger.failures else None,
            ),
            narrative={"degraded_reason": "NO_VIABLE_TIMEFRAME"},
            pipeline=ledger.to_dict(),
        )

    # Back to Decimal at the money boundary: engines compute in float to match
    # the reference implementation, prices are persisted and sized in Decimal.
    policy = risk_policy_for(decision_timeframe)
    atr = float(volatility.get("atr") or 0.0)
    entry_f = bars[-1].close
    stop_distance = atr * policy.stop_atr_multiple
    entry = Decimal(str(entry_f))
    stop = entry - Decimal(str(stop_distance))
    risk = run_risk_engine(entry=entry, stop=stop)

    plan_sanity = run_plan_sanity_engine(
        entry=entry_f,
        stop=entry_f - stop_distance,
        targets=[entry_f + stop_distance * r for r in policy.target_r],
        atr=atr,
        symbol=symbol,
        moment=as_of,
    )

    decision = run_decision_engine(scenarios, risk)
    decision["timeframe"] = decision_timeframe.value
    decision["timeframe_rationale"] = choice.rationale

    engines = {
        **evidence,
        "risk": risk,
        "plan_sanity": plan_sanity,
        "timeframe_selection": choice.to_dict(),
        "intelligence_by_tf": intelligence_by_tf,
    }

    # A plan that cannot survive its own costs is not a weaker recommendation,
    # it is one whose arithmetic never closes. Fail closed rather than publish it.
    if not plan_sanity["viable"]:
        return OrchestratorResult(
            agent_run_id=run_id,
            perceive=perceive,
            recall=recall,
            engines=engines,
            decision=fail_closed_no_trade(
                "PLAN_NOT_VIABLE", detail=", ".join(plan_sanity["failures"])
            ),
            narrative={
                "degraded_reason": "PLAN_NOT_VIABLE",
                "plan_failures": plan_sanity["failures"],
            },
            pipeline=ledger.to_dict(),
        )

    narrative: dict[str, Any] = {}
    prompt_hash: str | None = None
    try:
        prompt_hash = constitution().hash
    except PromptNotFound as exc:
        # A missing constitution is not a degraded run, it is an unguided model.
        # Nothing below should execute.
        return OrchestratorResult(
            agent_run_id=run_id,
            perceive=perceive,
            recall=recall,
            engines=engines,
            decision=fail_closed_no_trade("PROMPT_UNAVAILABLE", detail=str(exc)),
            narrative={"degraded_reason": "PROMPT_UNAVAILABLE", "detail": str(exc)},
            pipeline=ledger.to_dict(),
        )

    provider = llm
    if provider is None:
        try:
            provider = get_llm_provider()
        except ProviderConfigurationError as exc:
            return OrchestratorResult(
                agent_run_id=run_id,
                perceive=perceive,
                recall=recall,
                engines=engines,
                decision=fail_closed_no_trade("LLM_UNAVAILABLE", detail=str(exc)),
                narrative={"llm_unavailable": str(exc), "degraded_reason": "LLM_UNAVAILABLE"},
                pipeline=ledger.to_dict(),
                prompt_hash=prompt_hash,
            )

    resolved = provider

    async def _complete(messages: list[LLMMessage]) -> Any:
        return await resolved.complete(messages)

    outcome = await synthesize_decision(
        complete=_complete,
        symbol=symbol,
        evidence=_evidence_digest(engines),
        timeframe=decision_timeframe.value,
        visual=visual_evidence,
        engines=engines,
        atr=atr,
    )

    if outcome.ok and outcome.decision is not None:
        # The model's plan replaces the geometric placeholder, then goes through
        # the same cost gate: a plan the model wrote is not exempt from the
        # arithmetic that would have rejected it from anyone else.
        model_plan = outcome.decision
        assert model_plan.levels is not None
        model_sanity = run_plan_sanity_engine(
            entry=model_plan.levels.entry,
            stop=model_plan.levels.stop,
            targets=list(model_plan.levels.targets),
            atr=atr,
            symbol=symbol,
            moment=as_of,
        )
        engines["plan_sanity"] = model_sanity
        if not model_sanity["viable"]:
            return OrchestratorResult(
                agent_run_id=run_id,
                perceive=perceive,
                recall=recall,
                engines=engines,
                decision=fail_closed_no_trade(
                    "PLAN_NOT_VIABLE", detail=", ".join(model_sanity["failures"])
                ),
                narrative={
                    "degraded_reason": "PLAN_NOT_VIABLE",
                    "plan_failures": model_sanity["failures"],
                    "repairs": outcome.repairs,
                },
                pipeline=ledger.to_dict(),
                prompt_hash=prompt_hash,
            )
        decision = model_plan.model_dump(mode="json")
        decision["timeframe_rationale"] = choice.rationale
        model_name, provider_name = outcome.model, outcome.provider
        narrative = {
            "rationale": model_plan.rationale,
            "invalidation": model_plan.evidence.get("invalidation"),
            "condition": model_plan.evidence.get("condition"),
            "contradicting_evidence": model_plan.evidence.get("contradicting_evidence"),
            "attempts": outcome.attempts,
            "repairs": outcome.repairs,
        }
    else:
        model_name = provider_name = None
        if outcome.failure is not None:
            ledger.failures.append(outcome.failure)
        decision = fail_closed_no_trade("LLM_UNAVAILABLE", detail=outcome.detail)
        narrative = {
            "llm_unavailable": outcome.detail,
            "degraded_reason": "LLM_UNAVAILABLE",
            "failure_kind": outcome.kind.value if outcome.kind else None,
            "attempts": outcome.attempts,
            "repairs": outcome.repairs,
        }

    return OrchestratorResult(
        agent_run_id=run_id,
        perceive=perceive,
        recall=recall,
        engines=engines,
        decision=decision,
        narrative=narrative,
        pipeline=ledger.to_dict(),
        prompt_hash=prompt_hash,
        model=model_name,
        provider=provider_name,
    )


def _evidence_digest(engines: dict[str, Any]) -> str:
    """A compact, readable summary of the evidence for the prompt.

    Deliberately not the raw bundle: a geometry snapshot alone is thousands of
    tokens of anchor coordinates the model cannot use in prose, and spending the
    budget on them leaves nothing for the frames that matter. Whatever is
    elided here stays reachable through the tools, which is the division of
    labour the tool loop exists for.
    """
    structure = engines.get("structure", {})
    geometry = engines.get("geometry", {})
    mtf = engines.get("mtf", {})
    digest = {
        "structure": {
            "bias": structure.get("bias"),
            "shape": structure.get("shape"),
            "nearest_support": structure.get("nearest_support"),
            "nearest_resistance": structure.get("nearest_resistance"),
        },
        "regime": engines.get("market_intelligence", {}).get("regime"),
        "stance": engines.get("market_intelligence", {}).get("stance"),
        "mtf": {
            "alignment": mtf.get("alignment"),
            "trade_bias": mtf.get("trade_bias"),
            "conflict": mtf.get("conflict"),
            "roles": mtf.get("roles"),
        },
        "patterns": [
            {
                "type": p.get("pattern_type"),
                "status": p.get("status"),
                "stage": p.get("stage"),
                "confidence": p.get("confidence"),
                "target": p.get("projected_target"),
            }
            for p in geometry.get("patterns", [])
        ],
        "candlesticks": [c.get("name") for c in geometry.get("candlesticks", [])[:3]],
        "zones": engines.get("zones", {}).get("zones", [])[:4],
        "plan_sanity": engines.get("plan_sanity"),
        "timeframe": engines.get("timeframe_selection", {}).get("timeframe"),
    }
    return json.dumps(digest, ensure_ascii=False, default=str, indent=2)

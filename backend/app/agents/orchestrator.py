from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.core.errors import ProviderConfigurationError
from app.engines.bar import bars_from_candles
from app.engines.decision import run_decision_engine
from app.engines.liquidity import run_liquidity_engine
from app.engines.market_intelligence import run_market_intelligence_engine
from app.engines.mtf import run_mtf_engine
from app.engines.risk import run_risk_engine
from app.engines.scenario import run_scenario_engine
from app.engines.status import unavailable_engines
from app.engines.structure import run_structure_engine
from app.engines.volatility import run_volatility_engine
from app.engines.zones import run_zones_engine
from app.models.enums import RecommendationDirection
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


async def run_analysis_orchestrator(
    *,
    symbol: str,
    candles: list[Any],
    memories: list[dict[str, Any]] | None = None,
    llm: LLMProvider | None = None,
    mtf_context: dict[str, Any] | None = None,
) -> OrchestratorResult:
    if not candles:
        raise ValueError("Analysis requires at least one stored candle")

    run_id = uuid.uuid4()
    perceive = {"symbol": symbol, "candle_count": len(candles)}
    recall = {"memories": memories or [], "count": len(memories or [])}

    bars = bars_from_candles(candles)
    volatility = run_volatility_engine(bars)
    structure = run_structure_engine(bars)
    liquidity = run_liquidity_engine(bars)
    zones = run_zones_engine(bars)
    intelligence = run_market_intelligence_engine(bars)
    if mtf_context and "mtf" in mtf_context:
        mtf = mtf_context["mtf"]
        intelligence_by_tf = mtf_context.get("intelligence_by_tf", {})
    else:
        intelligence_by_tf = {"H1": intelligence}
        mtf = run_mtf_engine(intelligence_by_tf)

    # Scenarios run last among the evidence engines: their confidence is the
    # agreement between the others, so they need all of them.
    scenarios = run_scenario_engine(structure, volatility, liquidity, zones, mtf)

    evidence = {
        "volatility": volatility,
        "structure": structure,
        "liquidity": liquidity,
        "zones": zones,
        "scenarios": scenarios,
        "market_intelligence": intelligence,
        "mtf": mtf,
    }

    # Evidence first, decision second. An engine that cannot answer must stop the
    # run here: pricing risk and writing a narrative on top of missing evidence
    # produces a confident, plausible, unfounded recommendation, which is exactly
    # what the fail-closed contract exists to prevent (spec §95).
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
        )

    # Back to Decimal at the money boundary: engines compute in float to match
    # the reference implementation, prices are persisted and sized in Decimal.
    entry = Decimal(str(bars[-1].close))
    stop = entry - Decimal("0.0020")
    risk = run_risk_engine(entry=entry, stop=stop)
    decision = run_decision_engine(scenarios, risk)

    engines = {**evidence, "risk": risk, "intelligence_by_tf": intelligence_by_tf}

    narrative: dict[str, Any] = {}
    try:
        provider = llm or get_llm_provider()
        llm_out = await provider.complete(
            [
                LLMMessage(role="system", content="You are a trading analyst."),
                LLMMessage(
                    role="user",
                    content=f"Summarize {symbol} decision {decision['direction']}",
                ),
            ]
        )
        narrative = {"llm": llm_out.structured or {"summary": llm_out.content}}
    except ProviderConfigurationError as exc:
        # Fail closed: never emit BUY/SELL with confidence when the LLM layer is absent.
        decision = fail_closed_no_trade("LLM_UNAVAILABLE", detail=str(exc))
        narrative = {
            "llm_unavailable": str(exc),
            "degraded_reason": "LLM_UNAVAILABLE",
        }
    except Exception as exc:  # noqa: BLE001 — analysis path must fail closed
        decision = fail_closed_no_trade("LLM_UNAVAILABLE", detail=str(exc))
        narrative = {
            "llm_unavailable": str(exc),
            "degraded_reason": "LLM_UNAVAILABLE",
        }

    return OrchestratorResult(
        agent_run_id=run_id,
        perceive=perceive,
        recall=recall,
        engines=engines,
        decision=decision,
        narrative=narrative,
    )

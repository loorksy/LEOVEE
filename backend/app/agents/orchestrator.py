from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.engines.decision import run_decision_engine
from app.engines.liquidity import run_liquidity_engine
from app.engines.risk import run_risk_engine
from app.engines.scenario import run_scenario_engine
from app.engines.structure import run_structure_engine
from app.engines.volatility import OHLCBar, run_volatility_engine
from app.engines.zones import run_zones_engine
from app.providers.llm.base import LLMMessage
from app.providers.llm.openai import get_openai_provider


@dataclass
class OrchestratorResult:
    agent_run_id: uuid.UUID
    perceive: dict[str, Any] = field(default_factory=dict)
    recall: dict[str, Any] = field(default_factory=dict)
    engines: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    narrative: dict[str, Any] = field(default_factory=dict)


def bars_from_candles(candles: list[Any]) -> list[OHLCBar]:
    return [
        OHLCBar(open=c.open, high=c.high, low=c.low, close=c.close)
        for c in candles
    ]


async def run_analysis_orchestrator(
    *,
    symbol: str,
    candles: list[Any],
    memories: list[dict[str, Any]] | None = None,
) -> OrchestratorResult:
    run_id = uuid.uuid4()
    perceive = {"symbol": symbol, "candle_count": len(candles)}
    recall = {"memories": memories or [], "count": len(memories or [])}

    bars = bars_from_candles(candles)
    volatility = run_volatility_engine(bars)
    structure = run_structure_engine(bars)
    liquidity = run_liquidity_engine(bars)
    zones = run_zones_engine(bars)
    scenarios = run_scenario_engine(structure, volatility, liquidity)

    entry = Decimal(str(float(bars[-1].close))) if bars else Decimal("1.1")
    stop = entry - Decimal("0.0020")
    risk = run_risk_engine(entry=entry, stop=stop)
    decision = run_decision_engine(scenarios, risk)

    engines = {
        "volatility": volatility,
        "structure": structure,
        "liquidity": liquidity,
        "zones": zones,
        "scenarios": scenarios,
        "risk": risk,
    }

    llm = get_openai_provider(None)
    llm_out = await llm.complete(
        [
            LLMMessage(role="system", content="You are a trading analyst."),
            LLMMessage(
                role="user",
                content=f"Summarize {symbol} decision {decision['direction']}",
            ),
        ]
    )

    return OrchestratorResult(
        agent_run_id=run_id,
        perceive=perceive,
        recall=recall,
        engines=engines,
        decision=decision,
        narrative={"llm": llm_out.structured or {"summary": llm_out.content}},
    )

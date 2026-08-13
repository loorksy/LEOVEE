"""The stage graph: what runs, in what order, and what a failure does to the run.

Ported as a *shape* from AiChart's ``runUnifiedChartAgent`` — 2,600 lines whose
value is not the code but the graph it encodes and the failure discipline around
it. One visible agent over a fleet of specialists:

    market_data
        → (structure ∥ liquidity ∥ supply_demand ∥ geometry ∥ multi_timeframe)
        → timeframe_selection
        → risk → plan_sanity
        → final_decision

``execution_guard`` is deleted; ``plan_sanity`` takes its position as a
deterministic gate (D4).

**Three things are preserved deliberately, and each was learned the hard way.**

*Per-stage deadlines.* One hung provider must not hold the whole analysis. Each
stage gets its own budget and the run continues without it.

*Silent timeouts are ledgered.* A stage that resolves to a fallback instead of
raising leaves no exception behind. Without an explicit ledger entry, a run
whose specialists all timed out reports itself perfectly healthy with every
stage quietly empty — which is the worst possible failure because nothing
anywhere says anything is wrong. An empty result with no recorded failure for
that stage can only mean the deadline hit, and that inference is the mechanism.

*Independent specialists run concurrently.* They read the same bars and share
nothing, so running them in sequence multiplies the slowest provider by five for
no benefit.

**A stage failing does not end the run** unless the run cannot mean anything
without it. `market_data` is required — there is nothing to analyse. Everything
else degrades: the decision stage is told which evidence is missing and the
fail-closed contract decides what that is worth.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.errors import (
    AgentStage,
    StageFailure,
    ledger_silent_timeout,
    stage_failure_from_error,
)

__all__ = [
    "StageResult",
    "PipelineLedger",
    "STAGE_DEADLINES",
    "DEFAULT_STAGE_DEADLINE",
    "run_stage",
    "run_stages_concurrently",
]

#: Per-stage wall-clock budgets, in seconds.
#:
#: Deterministic engines are fast and get short deadlines — one that takes ten
#: seconds is wedged, not busy. Model-calling stages get room for a retry inside
#: the provider before the stage-level deadline fires, or the two mechanisms
#: fight and the retry never completes.
STAGE_DEADLINES: dict[AgentStage, float] = {
    AgentStage.MARKET_DATA: 15.0,
    AgentStage.STRUCTURE: 5.0,
    AgentStage.LIQUIDITY: 5.0,
    AgentStage.SUPPLY_DEMAND: 5.0,
    AgentStage.GEOMETRY: 8.0,
    AgentStage.MULTI_TIMEFRAME: 20.0,
    AgentStage.TIMEFRAME_SELECTION: 5.0,
    AgentStage.NEWS: 20.0,
    AgentStage.RISK: 5.0,
    AgentStage.PLAN_SANITY: 5.0,
    AgentStage.FINAL_DECISION: 90.0,
    AgentStage.DRAWING: 15.0,
}
DEFAULT_STAGE_DEADLINE = 30.0


def deadline_for(stage: AgentStage) -> float:
    return STAGE_DEADLINES.get(stage, DEFAULT_STAGE_DEADLINE)


@dataclass(slots=True)
class StageResult:
    stage: AgentStage
    value: Any = None
    failure: StageFailure | None = None
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.failure is None and self.value is not None


@dataclass(slots=True)
class PipelineLedger:
    """Everything that happened, including what did not."""

    results: dict[AgentStage, StageResult] = field(default_factory=dict)
    failures: list[StageFailure] = field(default_factory=list)

    def record(self, result: StageResult) -> StageResult:
        self.results[result.stage] = result
        if result.failure is not None and result.failure not in self.failures:
            self.failures.append(result.failure)
        return result

    def value(self, stage: AgentStage) -> Any:
        result = self.results.get(stage)
        return result.value if result else None

    def failed_stages(self) -> list[str]:
        return [failure.stage.value for failure in self.failures]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": {
                stage.value: {
                    "ok": result.ok,
                    "duration_ms": result.duration_ms,
                    "failure": result.failure.to_dict() if result.failure else None,
                }
                for stage, result in self.results.items()
            },
            "failures": [failure.to_dict() for failure in self.failures],
        }


async def run_stage(
    ledger: PipelineLedger,
    stage: AgentStage,
    work: Callable[[], Awaitable[Any]],
    *,
    deadline_seconds: float | None = None,
    provider: str | None = None,
) -> StageResult:
    """Run one stage under its deadline, recording whatever happened."""
    budget = deadline_seconds if deadline_seconds is not None else deadline_for(stage)
    started = time.monotonic()
    value: Any = None
    failure: StageFailure | None = None

    try:
        value = await asyncio.wait_for(work(), timeout=budget)
    except TimeoutError:
        failure = stage_failure_from_error(stage, TimeoutError("stage deadline"), provider)
    except asyncio.CancelledError:
        # A cancelled run is a deliberate stop. Recording it is right; swallowing
        # the cancellation is not, so it is re-raised after the ledger entry.
        ledger.record(
            StageResult(
                stage=stage,
                failure=stage_failure_from_error(stage, asyncio.CancelledError(), provider),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        raise
    except Exception as exc:  # noqa: BLE001 — every stage failure is classified
        failure = stage_failure_from_error(stage, exc, provider)

    result = StageResult(
        stage=stage,
        value=value,
        failure=failure,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    ledger.record(result)
    # Catches the stage that returned nothing without raising: the deadline is
    # the only thing that can produce that, and nothing else would notice.
    ledger_silent_timeout(ledger.failures, stage, value, budget)
    return result


async def run_stages_concurrently(
    ledger: PipelineLedger,
    stages: dict[AgentStage, Callable[[], Awaitable[Any]]],
) -> dict[AgentStage, StageResult]:
    """Run independent specialists at once, each under its own deadline."""
    names = list(stages)
    results = await asyncio.gather(
        *(run_stage(ledger, stage, stages[stage]) for stage in names),
        return_exceptions=False,
    )
    return dict(zip(names, results, strict=True))

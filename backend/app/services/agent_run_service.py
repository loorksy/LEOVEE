"""Persist the run, and everything that happened inside it.

``agent_runs`` and ``agent_traces`` existed with no writer. The admin
observability endpoint read an empty table forever, and every recommendation
carried an ``agent_run_id`` pointing at a row that was never created — a
foreign key in spirit that resolved to nothing, so no finished recommendation
could be traced back to the analysis that produced it.

That matters beyond tidiness. Three things depend on the run being on disk:

**Explaining a degraded answer.** ``NO_TRADE — ENGINE_UNAVAILABLE`` is honest
but not actionable. The trace says which stage, which code, how long it took and
whether it was retryable, and it says so after the request is gone.

**Attributing outcomes to decisions (M8).** ``prompt_hash`` is written here.
A calibration curve spanning a prompt change otherwise averages two different
analysts together and reads the spread as ordinary noise.

**Telling a quiet market from a broken pipeline.** A run with no failures that
declined, and a run that declined because four specialists timed out, look
identical from the outside and are completely different problems.

The traces inherit their scope from the parent run through the
``agent_traces_via_run`` policy — they carry no tenant columns of their own — so
the run must be flushed before its traces are added, or the policy has no parent
to find and the insert is rejected.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import OrchestratorResult
from app.agents.prompts import Prompt
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.learning import AgentRun, AgentRunStatus, AgentTrace
from app.services.prompt_registry_service import record_prompt_version

logger = structlog.get_logger(__name__)

__all__ = ["persist_agent_run", "TRACE_EVENT_TYPES"]

#: The event vocabulary written to ``agent_traces``. Kept small and closed: a
#: free-form event type turns the trace into prose nothing can query.
TRACE_EVENT_TYPES = ("stage", "failure", "decision")

#: agent_traces.event_type is String(64) and payloads are JSONB; the operator
#: detail is already bounded at classification, but a stage value from a future
#: enum should truncate rather than fail the whole write.
_MAX_EVENT_TYPE = 64


async def persist_agent_run(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    result: OrchestratorResult,
    symbol: str,
    trigger: str = "analysis",
    started_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
    prompt: Prompt | None = None,
) -> AgentRun | None:
    """Write the run and its traces. Returns None if the write failed.

    It really does not raise, which the docstring used to claim without the code
    backing it. The analysis has already completed by the time this runs, and
    losing a finished recommendation over a bookkeeping row is the wrong trade —
    but a failure that vanishes silently is the wrong trade in the other
    direction, so it is logged at warning with the run id and the caller can see
    that nothing was written.
    """
    try:
        return await _persist(
            session,
            tenant,
            result=result,
            symbol=symbol,
            trigger=trigger,
            started_at=started_at,
            user_id=user_id,
            prompt=prompt,
        )
    except Exception as exc:  # noqa: BLE001 — the analysis must survive this
        logger.warning(
            "agent_run_persist_failed",
            agent_run_id=str(result.agent_run_id),
            error=str(exc)[:300],
        )
        return None


async def _persist(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    result: OrchestratorResult,
    symbol: str,
    trigger: str,
    started_at: datetime | None,
    user_id: uuid.UUID | None,
    prompt: Prompt | None,
) -> AgentRun:
    await bind_workspace_rls(session, tenant)

    if prompt is not None:
        await record_prompt_version(session, prompt)

    decision = result.decision or {}
    degraded = bool(decision.get("degraded"))
    now = datetime.now(UTC)

    run = AgentRun(
        id=result.agent_run_id,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=user_id,
        symbol=symbol.upper(),
        trigger=trigger,
        state="COMPLETED",
        # A degraded run *completed* — it reached a defensible answer through
        # the fail-closed path. FAILED is reserved for a run that crashed, and
        # conflating them hides the difference between a refusal and a bug.
        status=AgentRunStatus.COMPLETED,
        decision=str(decision.get("direction")) if decision.get("direction") else None,
        model=result.model,
        provider=result.provider,
        prompt_hash=result.prompt_hash,
        tool_calls_count=int(result.narrative.get("tool_calls", 0) or 0),
        memories_retrieved_count=int(result.recall.get("count", 0) or 0),
        started_at=started_at or now,
        completed_at=now,
        error=str(decision.get("degraded_reason")) if degraded else None,
    )
    session.add(run)
    # Flush before the traces: their RLS policy scopes them through the parent
    # row, so an unflushed run means the policy finds no parent and rejects.
    await session.flush()

    for seq, (event_type, payload) in enumerate(_trace_events(result)):
        session.add(
            AgentTrace(
                id=uuid.uuid4(),
                agent_run_id=run.id,
                seq=seq,
                event_type=event_type[:_MAX_EVENT_TYPE],
                payload_json=payload,
                created_at=now,
            )
        )
    await session.flush()
    return run


def _trace_events(result: OrchestratorResult) -> list[tuple[str, dict[str, Any]]]:
    """One row per thing worth explaining later.

    Stages and failures are recorded separately even though a failed stage
    appears in both. The stage row carries timing and is queryable for
    "how long does geometry take"; the failure row carries the taxonomy code and
    is queryable for "how often does the provider 429". Merging them makes both
    questions awkward.
    """
    events: list[tuple[str, dict[str, Any]]] = []
    pipeline = result.pipeline or {}

    for stage, detail in (pipeline.get("stages") or {}).items():
        events.append(("stage", {"stage": stage, **detail}))

    for failure in pipeline.get("failures") or []:
        events.append(("failure", dict(failure)))

    decision = result.decision or {}
    events.append(
        (
            "decision",
            {
                "direction": decision.get("direction"),
                "confidence": decision.get("confidence"),
                "degraded": bool(decision.get("degraded")),
                "degraded_reason": decision.get("degraded_reason"),
                "detail": decision.get("detail"),
                "timeframe": decision.get("timeframe"),
                "timeframe_rationale": decision.get("timeframe_rationale"),
                # Named unavailable engines are the single most useful thing in
                # the trace: they turn "degraded" into "which one".
                "unavailable_engines": result.narrative.get("unavailable_engines"),
                "plan_failures": result.narrative.get("plan_failures"),
            },
        )
    )
    return events

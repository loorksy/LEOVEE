"""The run and its traces reach the database, and stay inside the workspace.

`agent_runs` and `agent_traces` had no writer at all: the admin observability
endpoint read an empty table forever and every recommendation carried an
`agent_run_id` pointing at a row that was never created.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import OrchestratorResult
from app.agents.prompts import constitution
from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.learning import AgentRun, AgentTrace
from app.models.prompt import PromptVersion
from app.services.agent_run_service import persist_agent_run
from app.tests.conftest import seed_user_org


def _result(**overrides: Any) -> OrchestratorResult:
    base = OrchestratorResult(
        agent_run_id=uuid.uuid4(),
        perceive={"symbol": "XAUUSD", "candle_count": 140},
        recall={"memories": [], "count": 3},
        engines={},
        decision={"direction": "BUY", "confidence": 0.7},
        narrative={},
        pipeline={
            "stages": {"geometry": {"ok": True, "duration_ms": 12, "failure": None}},
            "failures": [],
        },
        prompt_hash="a" * 64,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


async def _tenant(session: AsyncSession, *, email: str, slug: str) -> TenantContext:
    user, _org, _member = await seed_user_org(session, email=email, slug=slug)
    ctx = await resolve_tenant_context(session, user.id)
    await bind_workspace_rls(session, ctx)
    return ctx


@pytest.mark.asyncio
async def test_a_run_and_its_traces_are_written(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="run1@example.com", slug="run1")
    result = _result()

    run = await persist_agent_run(
        db_session, tenant, result=result, symbol="xauusd", started_at=datetime.now(UTC)
    )
    assert run is not None, "the run was not written"

    assert run.id == result.agent_run_id
    assert run.symbol == "XAUUSD"
    assert run.prompt_hash == "a" * 64
    assert run.memories_retrieved_count == 3

    traces = (
        (
            await db_session.execute(
                select(AgentTrace).where(AgentTrace.agent_run_id == run.id).order_by(AgentTrace.seq)
            )
        )
        .scalars()
        .all()
    )
    kinds = [t.event_type for t in traces]
    assert "stage" in kinds
    assert kinds[-1] == "decision"
    assert [t.seq for t in traces] == list(range(len(traces)))


@pytest.mark.asyncio
async def test_a_degraded_run_records_why_and_still_counts_as_completed(
    db_session: AsyncSession,
) -> None:
    """A degraded run reached a defensible answer through the fail-closed path.

    FAILED is reserved for a run that crashed; conflating them hides the
    difference between a refusal and a bug.
    """
    tenant = await _tenant(db_session, email="run2@example.com", slug="run2")
    result = _result(
        decision={
            "direction": "NO_TRADE",
            "confidence": None,
            "degraded": True,
            "degraded_reason": "ENGINE_UNAVAILABLE",
            "detail": "geometry",
        },
        narrative={"unavailable_engines": ["geometry"]},
        pipeline={
            "stages": {},
            "failures": [
                {
                    "stage": "final_decision",
                    "code": "rate_limit",
                    "retryable": True,
                    "operator_detail": "HTTP 429",
                    "provider": "openai",
                }
            ],
        },
    )

    run = await persist_agent_run(db_session, tenant, result=result, symbol="XAUUSD")
    assert run is not None, "the run was not written"
    assert run.status.value == "COMPLETED"
    assert run.error == "ENGINE_UNAVAILABLE"
    assert run.decision == "NO_TRADE"

    traces = (
        (
            await db_session.execute(
                select(AgentTrace).where(AgentTrace.agent_run_id == run.id).order_by(AgentTrace.seq)
            )
        )
        .scalars()
        .all()
    )
    failures = [t for t in traces if t.event_type == "failure"]
    assert failures[0].payload_json["code"] == "rate_limit"

    decision_row = [t for t in traces if t.event_type == "decision"][0]
    # Naming the engine is what turns "degraded" into something actionable.
    assert decision_row.payload_json["unavailable_engines"] == ["geometry"]


@pytest.mark.asyncio
async def test_the_prompt_text_is_catalogued_once(db_session: AsyncSession) -> None:
    """The registry on disk holds the text; this holds what was actually sent,
    so a run recorded months ago is still traceable after the file changes."""
    tenant = await _tenant(db_session, email="run3@example.com", slug="run3")
    prompt = constitution()

    await persist_agent_run(db_session, tenant, result=_result(), symbol="XAUUSD", prompt=prompt)
    await persist_agent_run(db_session, tenant, result=_result(), symbol="XAUUSD", prompt=prompt)

    rows = (
        (await db_session.execute(select(PromptVersion).where(PromptVersion.hash == prompt.hash)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].body == prompt.body


@pytest.mark.asyncio
async def test_a_run_is_invisible_from_another_workspace(db_session: AsyncSession) -> None:
    """Traces carry no tenant columns of their own — they inherit scope from the
    parent run through agent_traces_via_run. That indirection is worth testing
    directly, because a policy that resolves to no parent silently returns
    nothing rather than failing."""
    owner = await _tenant(db_session, email="owner@example.com", slug="owner-org")
    result = _result()
    run = await persist_agent_run(db_session, owner, result=result, symbol="XAUUSD")
    assert run is not None, "the run was not written"
    await db_session.commit()

    # Binds RLS to a different workspace as a side effect.
    await _tenant(db_session, email="other@example.com", slug="other-org")

    assert (await db_session.scalar(select(AgentRun).where(AgentRun.id == run.id))) is None
    traces = (
        (await db_session.execute(select(AgentTrace).where(AgentTrace.agent_run_id == run.id)))
        .scalars()
        .all()
    )
    assert traces == []

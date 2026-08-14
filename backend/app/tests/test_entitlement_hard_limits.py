"""Isolated hard-limit tests for entitlements (Batch 6 — §7 phase 38 expansion).

These tests call the service layer directly (no HTTP transport, no OANDA
market fetch, no real LLM provider) so a plan limit of ``0`` proves the
``EntitlementError`` is raised *before* any downstream work — analysis
engines, chat/LLM calls, or MCP tool dispatch never execute once the
metric cap is exceeded. Practice-only OANDA usage is unaffected because the
market-data layer is never reached in the blocked path.

Note: `SET LOCAL` RLS session variables are transaction-scoped, so
`bind_workspace_rls` is (re)applied immediately before the call under test,
after any `commit()` — mirroring how the request lifecycle rebinds RLS on
every inbound request.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.conversation import Conversation, ConversationMode
from app.models.enums import PlanCode
from app.models.mcp import McpAuditEvent
from app.models.plan import Plan
from app.services import analysis_service, chat_service, entitlement_service, market_data
from app.services.entitlement_service import EntitlementError
from app.tests.conftest import seed_user_org
from app.tests.doubles.llm import FakeLLMProvider


async def _cap_free_plan(db_session: AsyncSession, *, limit_key: str, cap: int) -> Plan:
    plan = await db_session.scalar(select(Plan).where(Plan.code == PlanCode.FREE))
    assert plan is not None
    plan.limits_json = {**(plan.limits_json or {}), limit_key: cap}
    await db_session.flush()
    return plan


@pytest.mark.asyncio
async def test_analysis_run_hard_limit_blocks_before_market_fetch(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§38 — analysis.run must be rejected in isolation with no market-data call."""
    user, org, _ = await seed_user_org(
        db_session, email="analysis-limit@example.com", slug="analysis-limit"
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    await _cap_free_plan(db_session, limit_key="analysis_runs_per_month", cap=0)
    await db_session.commit()
    await bind_workspace_rls(db_session, ctx)

    async def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("market data must not be fetched once the hard limit is hit")

    monkeypatch.setattr(market_data, "fetch_and_store_candles", _fail_if_called)

    with pytest.raises(EntitlementError) as exc_info:
        await analysis_service.run_analysis(db_session, ctx, symbol="XAUUSD")

    assert exc_info.value.code == "limit_exceeded"


@pytest.mark.asyncio
async def test_chat_send_hard_limit_blocks_before_llm_call(
    db_session: AsyncSession,
) -> None:
    """§38 — chat.send must be rejected in isolation without invoking the LLM provider."""
    user, org, _ = await seed_user_org(
        db_session, email="chat-limit@example.com", slug="chat-limit"
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    await _cap_free_plan(db_session, limit_key="messages_per_month", cap=0)
    await db_session.commit()
    await bind_workspace_rls(db_session, ctx)

    conversation = Conversation(
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        title="Limit test",
        mode=ConversationMode.CHAT,
        symbol="XAUUSD",
    )
    db_session.add(conversation)
    await db_session.flush()

    fake_llm = FakeLLMProvider()

    with pytest.raises(EntitlementError) as exc_info:
        await chat_service.run_chat_turn(
            db_session,
            ctx,
            conversation,
            user_content="What is the bias on XAUUSD?",
            llm=fake_llm,
        )

    assert exc_info.value.code == "limit_exceeded"
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_mcp_call_hard_limit_blocks_before_tool_dispatch(
    db_session: AsyncSession,
) -> None:
    """§38 — mcp.call must be rejected in isolation with no tool dispatch or audit row."""
    from app.mcp import runtime as mcp_runtime

    user, org, _ = await seed_user_org(db_session, email="mcp-limit@example.com", slug="mcp-limit")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    await _cap_free_plan(db_session, limit_key="mcp_calls_per_month", cap=0)
    await db_session.commit()
    await bind_workspace_rls(db_session, ctx)

    with pytest.raises(EntitlementError) as exc_info:
        await mcp_runtime.invoke_tool(
            db_session,
            ctx,
            tool_name="workspace.get_context",
            arguments={},
        )

    assert exc_info.value.code == "limit_exceeded"
    audit_rows = await db_session.execute(
        select(McpAuditEvent).where(McpAuditEvent.workspace_id == ctx.workspace_id)
    )
    assert list(audit_rows.scalars().all()) == []


@pytest.mark.asyncio
async def test_analysis_run_allowed_when_under_cap(db_session: AsyncSession) -> None:
    """Sanity control: a cap above current usage does not raise."""
    user, org, _ = await seed_user_org(
        db_session, email="analysis-ok@example.com", slug="analysis-ok"
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    await _cap_free_plan(db_session, limit_key="analysis_runs_per_month", cap=5)
    await db_session.commit()
    await bind_workspace_rls(db_session, ctx)

    await entitlement_service.check_metric_limit(db_session, ctx, "analysis.run")


@pytest.mark.asyncio
async def test_check_metric_limit_ignores_unrelated_metrics(db_session: AsyncSession) -> None:
    """A cap on one metric must not block a different metric (isolation across metrics)."""
    user, org, _ = await seed_user_org(
        db_session, email="cross-metric@example.com", slug="cross-metric"
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)
    await _cap_free_plan(db_session, limit_key="analysis_runs_per_month", cap=0)
    await db_session.commit()
    await bind_workspace_rls(db_session, ctx)

    # analysis.run is capped at zero, but mcp.call has no configured limit key set here.
    await entitlement_service.check_metric_limit(db_session, ctx, "mcp.call")
    with pytest.raises(EntitlementError):
        await entitlement_service.check_metric_limit(db_session, ctx, "analysis.run")

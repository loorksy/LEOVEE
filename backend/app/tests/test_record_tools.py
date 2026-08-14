"""The workspace record tools: bounded reads of the tenant's own rows.

Two properties carry the weight here and both get their own tests: the tools
refuse to run without a bound workspace, and a context bound to workspace B
sees none of workspace A's rows — the scoping is RLS plus the tenant on the
context, never an argument.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import TOOLS, ToolContext, dispatch_tool, record_tools
from app.agents.tools.record_tools import DEFAULT_LIMIT, MAX_LIMIT, _limit
from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.base import OrganizationMemberRole
from app.models.enums import RecommendationDirection
from app.services import (
    alert_service,
    chart_semantic_service,
    journal_service,
    recommendation_service,
    trade_service,
    watchlist_service,
)
from app.services.recommendations.reevaluation import (
    ReevaluationReason,
    ReevaluationTrigger,
    TriggerOutcome,
    record_trigger,
)
from app.services.recommendations.revisions import RevisionReason, record_revision
from app.tests.conftest import seed_user_org

RECORD_TOOL_NAMES = {
    "get_workspace_context",
    "list_recommendations",
    "get_recommendation",
    "get_recommendation_revisions",
    "get_reevaluation_history",
    "list_trades",
    "list_journal_entries",
    "list_alerts",
    "list_watchlists",
    "list_chart_annotations",
    "list_theses",
}


def _fake_tenant() -> TenantContext:
    return TenantContext(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        organization_member_id=uuid.uuid4(),
        role=OrganizationMemberRole.ORG_OWNER,
        workspace_id=uuid.uuid4(),
        workspace_member_id=uuid.uuid4(),
    )


class TestSurface:
    pytestmark = pytest.mark.no_db

    def test_every_mandated_tool_is_registered(self) -> None:
        assert {spec.name for spec in record_tools.TOOLS} == RECORD_TOOL_NAMES
        assert set(TOOLS) >= RECORD_TOOL_NAMES

    def test_every_record_tool_is_workspace_scoped(self) -> None:
        for spec in record_tools.TOOLS:
            assert spec.scope == "workspace", spec.name

    def test_no_tool_takes_a_scope_id_as_an_argument(self) -> None:
        """Workspace comes from the bound context; a parameter would be a hole."""
        for spec in record_tools.TOOLS:
            properties = spec.parameters.get("properties", {})
            for forbidden in ("workspace_id", "tenant_id", "user_id"):
                assert forbidden not in properties, f"{spec.name} accepts {forbidden}"

    async def test_an_unbound_context_is_refused_for_every_record_tool(self) -> None:
        # Refusal happens before the handler runs, so no session is needed.
        context = ToolContext(session=cast(Any, None))
        for spec in record_tools.TOOLS:
            result = await dispatch_tool(context, spec.name, {})
            assert result == {"error": "workspace_context_required", "detail": spec.name}

    def test_list_output_is_bounded(self) -> None:
        assert _limit({}) == DEFAULT_LIMIT
        assert _limit({"limit": 5}) == 5
        assert _limit({"limit": 100_000}) == MAX_LIMIT
        assert _limit({"limit": 0}) == 1
        assert _limit({"limit": -3}) == 1

    async def test_workspace_context_comes_from_the_bound_identity(self) -> None:
        tenant = _fake_tenant()
        context = ToolContext(session=cast(Any, None), tenant=tenant)
        result = await dispatch_tool(context, "get_workspace_context", {})
        assert result == {
            "workspace_id": str(tenant.workspace_id),
            "tenant_id": str(tenant.tenant_id),
            "user_id": str(tenant.user_id),
        }

    async def test_two_identities_report_two_different_answers(self) -> None:
        """The hardcoded MCP version answered the same for everyone; this must not."""
        first = await dispatch_tool(
            ToolContext(session=cast(Any, None), tenant=_fake_tenant()),
            "get_workspace_context",
            {},
        )
        second = await dispatch_tool(
            ToolContext(session=cast(Any, None), tenant=_fake_tenant()),
            "get_workspace_context",
            {},
        )
        assert first["workspace_id"] != second["workspace_id"]


@pytest.fixture
async def ctx(db_session: AsyncSession) -> TenantContext:
    user, _org, _ = await seed_user_org(db_session, email="rt@example.com", slug="rt")
    await db_session.commit()
    return await resolve_tenant_context(db_session, user.id)


@pytest.fixture
async def contexts(db_session: AsyncSession) -> tuple[TenantContext, TenantContext]:
    """Two fully separate tenants, each with one workspace."""
    user_a, _org_a, _ = await seed_user_org(db_session, email="rt-a@example.com", slug="rt-a")
    user_b, _org_b, _ = await seed_user_org(db_session, email="rt-b@example.com", slug="rt-b")
    await db_session.commit()
    ctx_a = await resolve_tenant_context(db_session, user_a.id)
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    return ctx_a, ctx_b


async def _seed_recommendation(session: AsyncSession, tenant: TenantContext) -> uuid.UUID:
    rec = await recommendation_service.create_recommendation(
        session,
        tenant,
        symbol_code="XAUUSD",
        direction=RecommendationDirection.BUY,
    )
    await session.commit()
    return rec.id


class TestRecordReads:
    async def test_recommendations_come_back_as_cards_newest_first(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        first = await _seed_recommendation(db_session, ctx)
        second = await _seed_recommendation(db_session, ctx)

        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "list_recommendations", {}
        )
        assert result["count"] == 2
        assert [card["id"] for card in result["recommendations"]] == [str(second), str(first)]
        card = result["recommendations"][0]
        assert card["symbol"] == "XAUUSD"
        assert card["direction"] == "BUY"
        assert "headline" in card and "badges" in card

    async def test_the_limit_argument_is_honoured(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        for _ in range(3):
            await _seed_recommendation(db_session, ctx)
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "list_recommendations",
            {"limit": 2},
        )
        assert result["count"] == 2

    async def test_get_recommendation_by_id(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        rec_id = await _seed_recommendation(db_session, ctx)
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_recommendation",
            {"recommendation_id": str(rec_id)},
        )
        assert result["id"] == str(rec_id)
        assert result["symbol"] == "XAUUSD"

    async def test_a_missing_recommendation_is_not_found_as_data(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_recommendation",
            {"recommendation_id": str(uuid.uuid4())},
        )
        assert result["error"] == "NOT_FOUND"

    async def test_a_malformed_id_comes_back_as_error_data(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_recommendation",
            {"recommendation_id": "not-a-uuid"},
        )
        assert result["error"] == "ValueError"

    async def test_revisions_read_oldest_first_and_name_the_live_status(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        rec_id = await _seed_recommendation(db_session, ctx)
        rec = await recommendation_service.get_recommendation(db_session, ctx, rec_id)
        assert rec is not None
        await record_revision(db_session, ctx, rec, reason=RevisionReason.CREATED)
        await record_revision(
            db_session, ctx, rec, reason=RevisionReason.MANUAL, note="looked again"
        )
        await db_session.commit()

        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_recommendation_revisions",
            {"recommendation_id": str(rec_id)},
        )
        assert result["count"] == 2
        assert [row["seq"] for row in result["revisions"]] == [0, 1]
        assert [row["reason"] for row in result["revisions"]] == ["created", "manual"]
        # The revision-vs-live-row distinction: history declares, the row is now.
        assert result["live_status"] == rec.status.value
        assert "declared_status" in result["revisions"][0]
        assert "distinction" in result

    async def test_revisions_for_an_unknown_recommendation_are_not_found(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_recommendation_revisions",
            {"recommendation_id": str(uuid.uuid4())},
        )
        assert result["error"] == "NOT_FOUND"

    async def test_reevaluation_history_lists_the_whole_ledger(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        rec_id = await _seed_recommendation(db_session, ctx)
        trigger = ReevaluationTrigger(
            recommendation_id=rec_id,
            symbol="XAUUSD",
            reason=ReevaluationReason.USER_REQUEST,
            detail="the user asked",
        )
        written = await record_trigger(db_session, ctx, trigger, outcome=TriggerOutcome.REQUESTED)
        assert written is True
        await db_session.commit()

        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_reevaluation_history",
            {"recommendation_id": str(rec_id)},
        )
        assert result["count"] == 1
        row = result["history"][0]
        assert row["reason"] == "user_request"
        assert row["outcome"] == "requested"
        assert row["detail"] == "the user asked"

    async def test_trades_are_listed_with_symbol_codes(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        await trade_service.create_trade_idea(
            db_session, ctx, symbol_code="XAUUSD", direction=RecommendationDirection.SELL
        )
        await db_session.commit()
        result = await dispatch_tool(ToolContext(session=db_session, tenant=ctx), "list_trades", {})
        assert result["count"] == 1
        assert result["trades"][0]["symbol"] == "XAUUSD"
        assert result["trades"][0]["direction"] == "SELL"
        assert result["trades"][0]["status"] == "IDEA"

    async def test_journal_entries_are_listed(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        await journal_service.create_entry(
            db_session, ctx, title="Patience", notes="waited for the close", tags=["discipline"]
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "list_journal_entries", {}
        )
        assert result["count"] == 1
        assert result["entries"][0]["title"] == "Patience"
        assert result["entries"][0]["tags"] == ["discipline"]

    async def test_alerts_are_listed_and_bounded(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        for i in range(3):
            await alert_service.create_alert(
                db_session,
                ctx,
                alert_type="PRICE",
                symbol_code="XAUUSD",
                condition={"op": "gte", "price": 2000 + i},
                channels={"inapp": True},
            )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "list_alerts", {"limit": 2}
        )
        assert result["count"] == 2
        assert result["alerts"][0]["type"] == "PRICE"
        assert result["alerts"][0]["active"] is True

    async def test_watchlists_include_their_items(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        wl = await watchlist_service.create_watchlist(db_session, ctx, name="Metals")
        await watchlist_service.add_symbol(
            db_session, ctx, watchlist_id=wl.id, symbol_code="XAUUSD"
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "list_watchlists", {}
        )
        assert result["count"] == 1
        listed = result["watchlists"][0]
        assert listed["name"] == "Metals"
        assert [item["code"] for item in listed["symbols"]] == ["XAUUSD"]

    async def test_chart_annotations_are_listed(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        # This service does not bind RLS itself; the writer binds before writing.
        await bind_workspace_rls(db_session, ctx)
        await chart_semantic_service.create_annotation(
            db_session,
            ctx,
            semantic_type="DRAW_LEVEL",
            geometry_json={"anchors": [{"ts": "2026-01-01T00:00:00+00:00", "price": 2000.0}]},
            style_json={},
            publish=False,
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "list_chart_annotations", {}
        )
        assert result["count"] == 1
        assert result["annotations"][0]["semantic_type"] == "DRAW_LEVEL"

    async def test_theses_are_listed(self, db_session: AsyncSession, ctx: TenantContext) -> None:
        rec_id = await _seed_recommendation(db_session, ctx)
        rec = await recommendation_service.get_recommendation(db_session, ctx, rec_id)
        assert rec is not None
        await recommendation_service.spawn_thesis_from_recommendation(
            db_session, ctx, rec, statement="Gold holds the level"
        )
        await db_session.commit()
        result = await dispatch_tool(ToolContext(session=db_session, tenant=ctx), "list_theses", {})
        assert result["count"] == 1
        assert result["theses"][0]["statement"] == "Gold holds the level"
        assert result["theses"][0]["recommendation_id"] == str(rec_id)


class TestTwoWorkspaceIsolation:
    """Rows seeded under workspace A must be invisible to a context bound to B."""

    async def test_recommendations_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await _seed_recommendation(db_session, ctx_a)
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_recommendations", {}
        )
        assert result == {"count": 0, "recommendations": []}

    async def test_a_foreign_recommendation_reads_as_not_found(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        rec_id = await _seed_recommendation(db_session, ctx_a)
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b),
            "get_recommendation",
            {"recommendation_id": str(rec_id)},
        )
        # Indistinguishable from a nonexistent id: no cross-workspace probing.
        assert result["error"] == "NOT_FOUND"

    async def test_foreign_revisions_read_as_not_found(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        rec_id = await _seed_recommendation(db_session, ctx_a)
        rec = await recommendation_service.get_recommendation(db_session, ctx_a, rec_id)
        assert rec is not None
        await record_revision(db_session, ctx_a, rec, reason=RevisionReason.CREATED)
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b),
            "get_recommendation_revisions",
            {"recommendation_id": str(rec_id)},
        )
        assert result["error"] == "NOT_FOUND"

    async def test_foreign_reevaluation_history_reads_as_not_found(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        rec_id = await _seed_recommendation(db_session, ctx_a)
        trigger = ReevaluationTrigger(
            recommendation_id=rec_id,
            symbol="XAUUSD",
            reason=ReevaluationReason.USER_REQUEST,
            detail="the user asked",
        )
        await record_trigger(db_session, ctx_a, trigger, outcome=TriggerOutcome.REQUESTED)
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b),
            "get_reevaluation_history",
            {"recommendation_id": str(rec_id)},
        )
        assert result["error"] == "NOT_FOUND"

    async def test_trades_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await trade_service.create_trade_idea(
            db_session, ctx_a, symbol_code="XAUUSD", direction=RecommendationDirection.BUY
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_trades", {}
        )
        assert result == {"count": 0, "trades": []}

    async def test_journal_entries_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await journal_service.create_entry(
            db_session, ctx_a, title="Private", notes="workspace A only"
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_journal_entries", {}
        )
        assert result == {"count": 0, "entries": []}

    async def test_alerts_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await alert_service.create_alert(
            db_session,
            ctx_a,
            alert_type="PRICE",
            symbol_code="XAUUSD",
            condition={"op": "gte", "price": 2000},
            channels={"inapp": True},
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_alerts", {}
        )
        assert result == {"count": 0, "alerts": []}

    async def test_watchlists_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        wl = await watchlist_service.create_watchlist(db_session, ctx_a, name="A's list")
        await watchlist_service.add_symbol(
            db_session, ctx_a, watchlist_id=wl.id, symbol_code="XAUUSD"
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_watchlists", {}
        )
        assert result == {"count": 0, "watchlists": []}

    async def test_chart_annotations_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await bind_workspace_rls(db_session, ctx_a)
        await chart_semantic_service.create_annotation(
            db_session,
            ctx_a,
            semantic_type="DRAW_LEVEL",
            geometry_json={"anchors": [{"ts": "2026-01-01T00:00:00+00:00", "price": 2000.0}]},
            style_json={},
            publish=False,
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_chart_annotations", {}
        )
        assert result == {"count": 0, "annotations": []}

    async def test_theses_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        rec_id = await _seed_recommendation(db_session, ctx_a)
        rec = await recommendation_service.get_recommendation(db_session, ctx_a, rec_id)
        assert rec is not None
        await recommendation_service.spawn_thesis_from_recommendation(db_session, ctx_a, rec)
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_theses", {}
        )
        assert result == {"count": 0, "theses": []}

    async def test_workspace_context_reports_only_the_bound_workspace(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "get_workspace_context", {}
        )
        assert result["workspace_id"] == str(ctx_b.workspace_id)
        assert result["workspace_id"] != str(ctx_a.workspace_id)

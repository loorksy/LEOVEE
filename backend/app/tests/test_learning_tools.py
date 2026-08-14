"""The learning-loop read tools: workspace record vs platform market fact.

Everything goes through ``dispatch_tool`` — the scope check, the error-as-data
contract and the gold gate all live on that path.

The isolation tests carry the doctrine this module encodes: strategy stats,
lessons and memories are the workspace's own record and must be invisible
across the boundary, while the market case tools are platform-scoped market
fact and must work with no workspace at all. A test asserting both directions
is what keeps "shared" and "private" from drifting into each other.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import TOOLS, ToolContext, dispatch_tool, learning_tools
from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import Timeframe
from app.models.learning import StrategyStat
from app.models.memory import Lesson
from app.providers.market.base import NormalizedCandle
from app.services import market_data, memory_service
from app.services.memory.cases.fingerprint import MIN_CANDLES
from app.tests.bars import swinging_bars
from app.tests.conftest import seed_user_org

LEARNING_TOOL_NAMES = {
    "get_strategy_stats",
    "get_strategy_support",
    "get_calibration",
    "get_trading_dna",
    "list_lessons",
    "search_memories",
    "get_performance_summary",
    "find_similar_cases",
    "get_case_outcome_stats",
}
PLATFORM_TOOL_NAMES = {"find_similar_cases", "get_case_outcome_stats"}


class TestSurfaceDeclaration:
    pytestmark = pytest.mark.no_db

    def test_every_mandated_tool_is_registered(self) -> None:
        assert {spec.name for spec in learning_tools.TOOLS} == LEARNING_TOOL_NAMES
        assert set(TOOLS) >= LEARNING_TOOL_NAMES

    def test_the_scope_split_is_exactly_the_doctrine(self) -> None:
        """Market cases are shared fact; everything else is the tenant's record."""
        for spec in learning_tools.TOOLS:
            expected = "platform" if spec.name in PLATFORM_TOOL_NAMES else "workspace"
            assert spec.scope == expected, spec.name

    def test_no_tool_takes_a_scope_id_as_an_argument(self) -> None:
        for spec in learning_tools.TOOLS:
            properties = spec.parameters.get("properties", {})
            for forbidden in ("workspace_id", "tenant_id", "user_id"):
                assert forbidden not in properties, f"{spec.name} accepts {forbidden}"

    async def test_workspace_tools_refuse_an_unbound_context(self) -> None:
        context = ToolContext(session=cast(Any, None))
        for spec in learning_tools.TOOLS:
            if spec.scope != "workspace":
                continue
            result = await dispatch_tool(context, spec.name, {})
            assert result == {"error": "workspace_context_required", "detail": spec.name}

    async def test_case_tools_validate_direction_before_touching_the_session(self) -> None:
        for name in PLATFORM_TOOL_NAMES:
            result = await dispatch_tool(
                ToolContext(session=cast(Any, None)), name, {"direction": "long"}
            )
            assert result["error"] == "ValueError"
            assert "buy" in result["detail"]


@pytest.fixture
async def ctx(db_session: AsyncSession) -> TenantContext:
    user, _org, _ = await seed_user_org(db_session, email="lt@example.com", slug="lt")
    await db_session.commit()
    return await resolve_tenant_context(db_session, user.id)


@pytest.fixture
async def contexts(db_session: AsyncSession) -> tuple[TenantContext, TenantContext]:
    user_a, _org_a, _ = await seed_user_org(db_session, email="lt-a@example.com", slug="lt-a")
    user_b, _org_b, _ = await seed_user_org(db_session, email="lt-b@example.com", slug="lt-b")
    await db_session.commit()
    ctx_a = await resolve_tenant_context(db_session, user_a.id)
    ctx_b = await resolve_tenant_context(db_session, user_b.id)
    return ctx_a, ctx_b


async def _seed_stat(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    strategy_code: str = "structure_uptrend_trending_m15",
    occurrences: int = 12,
    wins: int = 8,
) -> None:
    await bind_workspace_rls(session, tenant)
    session.add(
        StrategyStat(
            tenant_id=tenant.tenant_id,
            workspace_id=tenant.workspace_id,
            strategy_code=strategy_code,
            occurrences=occurrences,
            wins=wins,
            avg_r=Decimal("0.8"),
        )
    )
    await session.commit()


async def _seed_lesson(session: AsyncSession, tenant: TenantContext, statement: str) -> None:
    await bind_workspace_rls(session, tenant)
    session.add(
        Lesson(
            tenant_id=tenant.tenant_id,
            workspace_id=tenant.workspace_id,
            statement=statement,
            conditions_json={},
        )
    )
    await session.commit()


async def _seed_candles(session: AsyncSession, timeframe: Timeframe = Timeframe.M15) -> None:
    """Enough stored bars to fingerprint the current window."""
    bars = swinging_bars(
        (MIN_CANDLES // 10) + 4,
        drift=6.0,
        swing=9.0,
        bars_per_leg=5,
        interval=timedelta(minutes=15),
    )
    symbol = await market_data.get_or_create_symbol(session, "XAUUSD")
    await market_data.upsert_candles(
        session,
        symbol.id,
        [
            NormalizedCandle(
                symbol="XAUUSD",
                timeframe=timeframe,
                ts=bar.ts,
                open=Decimal(str(bar.open)),
                high=Decimal(str(bar.high)),
                low=Decimal(str(bar.low)),
                close=Decimal(str(bar.close)),
                volume=Decimal("100"),
                complete=True,
                source="test_double",
            )
            for bar in bars
        ],
    )
    await session.commit()


class TestWorkspaceReads:
    async def test_strategy_stats_read_back_as_written(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        await _seed_stat(db_session, ctx, occurrences=12, wins=8)
        await _seed_stat(db_session, ctx, strategy_code="liquidity_sweep_m5", occurrences=3, wins=1)

        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "get_strategy_stats", {}
        )
        assert result["count"] == 2
        # Most-used bucket first, raw counters, no derived rate.
        top = result["stats"][0]
        assert top["strategy_code"] == "structure_uptrend_trending_m15"
        assert top["occurrences"] == 12
        assert top["wins"] == 8
        assert "win_rate" not in top

    async def test_strategy_stats_filter_by_code(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        await _seed_stat(db_session, ctx)
        await _seed_stat(db_session, ctx, strategy_code="liquidity_sweep_m5")
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_strategy_stats",
            {"strategy_code": "liquidity_sweep_m5"},
        )
        assert result["count"] == 1
        assert result["stats"][0]["strategy_code"] == "liquidity_sweep_m5"

    async def test_an_empty_record_reads_as_no_support_not_as_silence(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        """The cold-start doctrine: the empty record never blocks, it labels."""
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "get_strategy_support",
            {"strategy_code": "structure_uptrend_trending_m15"},
        )
        assert result["support"]["level"] == "none"
        assert result["support"]["reason"] == "SUPPORT_NO_HISTORY"
        assert "no statistical support" in result["interpretation"]

    async def test_strategy_support_requires_a_code(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "get_strategy_support", {}
        )
        assert result["error"] == "ValueError"

    async def test_calibration_on_an_empty_workspace_is_zero_not_invented(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "get_calibration", {}
        )
        assert result == {
            "bin_count": 0,
            "bins": [],
            "predicted_total": 0,
            "realized_success_total": 0,
        }

    async def test_trading_dna_on_an_empty_workspace_is_honest_about_it(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "get_trading_dna", {}
        )
        assert result["evidence_window"]["closed_plans"] == 0
        assert result["evidence_window"]["reported_trades"] == 0
        assert result["metrics"], "the metric list itself must not vanish"
        for metric in result["metrics"]:
            # No closed plans: nothing may claim support, and each absence
            # carries its floor rather than a smoothed-over zero.
            assert metric["status"] != "supported", metric["key"]

    async def test_lessons_list_newest_first(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        await _seed_lesson(db_session, ctx, "Wait for the close")
        await _seed_lesson(db_session, ctx, "Respect the halt window")
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "list_lessons", {}
        )
        assert result["count"] == 2
        assert {row["statement"] for row in result["lessons"]} == {
            "Wait for the close",
            "Respect the halt window",
        }

    async def test_memory_search_requires_a_query(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "search_memories", {}
        )
        assert result["error"] == "ValueError"

    async def test_memory_search_finds_the_workspace_own_rows(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        await memory_service.store_memory(
            db_session,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            key="symbol:XAUUSD:sweep.bias",
            content={"fact": "sweeps resolve upward in the NY morning"},
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx),
            "search_memories",
            {"query": "sweep bias"},
        )
        assert result["count"] >= 1
        assert any(m["key"] == "symbol:XAUUSD:sweep.bias" for m in result["memories"])

    async def test_performance_summary_has_the_shape_the_ui_reads(
        self, db_session: AsyncSession, ctx: TenantContext
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx), "get_performance_summary", {}
        )
        assert set(result) >= {
            "as_of",
            "recommendations",
            "trade_ideas",
            "outcome_records",
            "calibration",
        }
        assert result["trade_ideas"] == 0


class TestTwoWorkspaceIsolation:
    async def test_strategy_stats_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await _seed_stat(db_session, ctx_a)
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "get_strategy_stats", {}
        )
        assert result == {"count": 0, "stats": []}

    async def test_lessons_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await _seed_lesson(db_session, ctx_a, "Workspace A's lesson")
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b), "list_lessons", {}
        )
        assert result == {"count": 0, "lessons": []}

    async def test_memories_do_not_cross_workspaces(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        ctx_a, ctx_b = contexts
        await memory_service.store_memory(
            db_session,
            tenant_id=ctx_a.tenant_id,
            workspace_id=ctx_a.workspace_id,
            key="symbol:XAUUSD:private.read",
            content={"fact": "workspace A only"},
        )
        await db_session.commit()
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b),
            "search_memories",
            {"query": "private read"},
        )
        assert result["count"] == 0

    async def test_one_workspace_outcomes_never_grade_anothers_support(
        self, db_session: AsyncSession, contexts: tuple[TenantContext, TenantContext]
    ) -> None:
        """The M8 exit criterion, through the tool surface."""
        ctx_a, ctx_b = contexts
        await _seed_stat(db_session, ctx_a, occurrences=40, wins=30)
        result = await dispatch_tool(
            ToolContext(session=db_session, tenant=ctx_b),
            "get_strategy_support",
            {"strategy_code": "structure_uptrend_trending_m15"},
        )
        assert result["support"]["level"] == "none"
        assert result["support"]["reason"] == "SUPPORT_NO_HISTORY"


class TestPlatformCaseMemory:
    async def test_too_little_history_declines_to_fingerprint(
        self, db_session: AsyncSession
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session), "find_similar_cases", {"direction": "buy"}
        )
        assert result["error"] == "ValueError"
        assert "not enough stored" in result["detail"]

    async def test_similar_cases_need_no_workspace_and_report_the_floor(
        self, db_session: AsyncSession
    ) -> None:
        """Platform market fact: an unbound context is the point, not a gap."""
        await _seed_candles(db_session)
        result = await dispatch_tool(
            ToolContext(session=db_session), "find_similar_cases", {"direction": "buy"}
        )
        assert "error" not in result
        assert result["min_similarity"] > 0
        assert result["probe_fingerprint"]
        assert result["cases"] == []

    async def test_thin_case_stats_withhold_rates_and_say_so(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_candles(db_session)
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_case_outcome_stats", {"direction": "sell"}
        )
        assert "error" not in result
        assert result["matched_cases"] == 0
        assert result["sufficient"] is False

    async def test_the_gold_gate_holds_on_this_surface_too(self, db_session: AsyncSession) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session),
            "find_similar_cases",
            {"direction": "buy", "symbol": "EURUSD"},
        )
        assert result["error"] == "UnknownSymbolError"

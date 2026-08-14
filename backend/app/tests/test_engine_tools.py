"""The engine read surface: every deterministic engine, dispatched as a tool.

Everything here goes through ``dispatch_tool`` rather than the handlers
directly, because the dispatcher is the only door the model has: the scope
check, the error-as-data contract and the gold gate all live on that path, and
a handler that works when called directly but misbehaves through dispatch is
broken in the only way that matters.

No two-workspace isolation tests appear here on purpose: every tool in
``engine_tools`` is platform-scoped, reading shared candles or shared news.
``news_events`` in particular is deliberately global (see the RLS coverage
exemptions), and ``test_news_needs_no_workspace_binding`` pins that decision.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import TOOLS, ToolContext, dispatch_tool, engine_tools
from app.engines.bar import OHLCBar
from app.models.enums import Timeframe
from app.models.news import NewsEvent
from app.providers.market.base import NormalizedCandle
from app.services import market_data
from app.tests.bars import flat_bars, swinging_bars

START = datetime(2026, 1, 1, tzinfo=UTC)

ENGINE_TOOL_NAMES = {
    "get_geometry",
    "get_zones",
    "get_liquidity",
    "get_volatility_regime",
    "get_mtf_bias",
    "get_price_context",
    "get_timeframe_read",
    "get_session_status",
    "get_news",
}

_INTERVAL = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
}

#: The handlers that never reach the database raise (or answer) before touching
#: the session, so a stand-in session exercises them without Postgres.
_NO_DB_CONTEXT = ToolContext(session=cast(Any, None))


def _uptrend(timeframe: Timeframe) -> list[OHLCBar]:
    """~115 bars of higher highs and higher lows — readable structure."""
    return swinging_bars(12, drift=6.0, swing=9.0, bars_per_leg=5, interval=_INTERVAL[timeframe])


async def _seed_series(session: AsyncSession, timeframe: Timeframe, series: list[OHLCBar]) -> None:
    symbol = await market_data.get_or_create_symbol(session, "XAUUSD")
    candles = [
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
        for bar in series
    ]
    await market_data.upsert_candles(session, symbol.id, candles)
    await session.flush()


async def _seed_news(
    session: AsyncSession,
    *,
    count: int,
    currency: str = "USD",
) -> None:
    for i in range(count):
        session.add(
            NewsEvent(
                source="test_double",
                published_at=START + timedelta(hours=i),
                headline=f"{currency} headline {i}",
                summary=f"summary {i}",
                currency=currency,
                relevance=Decimal("0.5"),
                market_impact="medium",
                url=f"https://example.com/{currency}/{i}",
                external_id=f"{currency}-{i}",
                raw_json={},
                ingested_at=datetime.now(UTC),
            )
        )
    await session.flush()


class TestSurfaceDeclaration:
    pytestmark = pytest.mark.no_db

    def test_every_engine_read_tool_is_registered(self) -> None:
        assert {spec.name for spec in engine_tools.TOOLS} == ENGINE_TOOL_NAMES
        assert set(TOOLS) >= ENGINE_TOOL_NAMES

    def test_every_engine_tool_is_platform_scoped(self) -> None:
        """Shared market facts: none of these may demand a workspace binding."""
        for spec in engine_tools.TOOLS:
            assert spec.scope == "platform", spec.name

    def test_every_engine_tool_declares_an_object_schema(self) -> None:
        for spec in engine_tools.TOOLS:
            assert spec.parameters.get("type") == "object", spec.name
            assert spec.description, spec.name

    def test_no_handler_takes_a_workspace_filter(self) -> None:
        """Workspace scope comes only from the bound session, never a parameter."""
        for spec in engine_tools.TOOLS:
            properties = spec.parameters.get("properties", {})
            for banned in ("workspace_id", "tenant_id", "user_id", "workspace", "tenant"):
                assert banned not in properties, f"{spec.name} exposes {banned}"


class TestSymbolAndTimeframeGates:
    pytestmark = pytest.mark.no_db

    @pytest.mark.parametrize("name", ["get_geometry", "get_mtf_bias", "get_session_status"])
    async def test_symbols_outside_the_allowlist_are_refused(self, name: str) -> None:
        """The gate raises rather than substituting gold; dispatch reports it."""
        result = await dispatch_tool(_NO_DB_CONTEXT, name, {"symbol": "EURUSD"})
        assert result["error"] == "UnknownSymbolError"

    async def test_non_stored_timeframes_are_refused(self) -> None:
        result = await dispatch_tool(_NO_DB_CONTEXT, "get_geometry", {"timeframe": "D1"})
        assert result["error"] == "ValueError"

    async def test_a_context_frame_cannot_be_the_decision_frame(self) -> None:
        """H4 gives context; asking the ladder to decide on it is a model mistake."""
        result = await dispatch_tool(_NO_DB_CONTEXT, "get_mtf_bias", {"timeframe": "H4"})
        assert result["error"] == "ValueError"
        assert "decision timeframe" in result["detail"]


class TestSessionStatusTool:
    pytestmark = pytest.mark.no_db

    async def test_answers_open_or_closed_with_a_stable_reason(self) -> None:
        result = await dispatch_tool(_NO_DB_CONTEXT, "get_session_status", {})
        assert isinstance(result["is_open"], bool)
        assert result["reason"] in {
            "MARKET_OPEN",
            "WEEKEND",
            "WEEK_CLOSED",
            "WEEK_NOT_OPEN_YET",
            "DAILY_MAINTENANCE_BREAK",
        }
        assert result["is_open"] is (result["reason"] == "MARKET_OPEN")
        assert result["symbol"] == "XAUUSD"

    async def test_reports_the_daily_halt_window(self) -> None:
        """[17:00, 18:00) New York, Monday-Thursday — the gold session model."""
        result = await dispatch_tool(_NO_DB_CONTEXT, "get_session_status", {})
        halt = result["daily_halt"]
        assert halt["timezone"] == "America/New_York"
        assert halt["start_hour"] == 17
        assert halt["end_hour"] == 18
        assert "Monday" in halt["days"]


class TestGeometryTool:
    async def test_snapshot_is_bounded_as_the_engine_bounds_it(
        self, db_session: AsyncSession
    ) -> None:
        series = _uptrend(Timeframe.M15)
        await _seed_series(db_session, Timeframe.M15, series)
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_geometry", {"timeframe": "M15"}
        )
        assert result["timeframe"] == "M15"
        assert result["candle_count"] == len(series)
        assert result["atr"] > 0
        assert len(result["patterns"]) <= 3
        for key in ("pivots", "trendlines", "channels", "patterns", "candlesticks"):
            assert isinstance(result[key], list), key
        # Status and stage travel with every pattern the decision stage reads.
        for pattern in result["patterns"]:
            assert pattern["status"] in {"forming", "completed", "invalidated"}
            assert "stage" in pattern

    async def test_too_few_bars_is_declared_not_invented(self, db_session: AsyncSession) -> None:
        await _seed_series(db_session, Timeframe.M15, _uptrend(Timeframe.M15)[:30])
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_geometry", {"timeframe": "M15"}
        )
        assert result["status"] == "unavailable"
        assert result["reason"] == "INSUFFICIENT_DATA"


class TestZonesTool:
    async def test_an_unconsumed_imbalance_is_reported_as_a_zone(
        self, db_session: AsyncSession
    ) -> None:
        # Quiet tape, one decisive bullish departure, then price holds above it.
        series = flat_bars(70, price=2000.0, spread=0.5, interval=timedelta(minutes=15))
        step = timedelta(minutes=15)
        last = series[-1].ts
        series.append(
            OHLCBar(ts=last + step, open=2000.0, high=2006.5, low=1999.7, close=2006.0, volume=0.0)
        )
        for j in range(10):
            series.append(
                OHLCBar(
                    ts=last + step * (j + 2),
                    open=2004.0,
                    high=2004.8,
                    low=2003.5,
                    close=2004.3,
                    volume=0.0,
                )
            )
        await _seed_series(db_session, Timeframe.M15, series)

        result = await dispatch_tool(
            ToolContext(session=db_session), "get_zones", {"timeframe": "M15"}
        )
        assert result["demand"], "the departure left an imbalance and it must be reported"
        zone = result["demand"][0]
        assert zone["type"] == "DEMAND"
        assert zone["low"] == pytest.approx(1999.7)
        assert zone["high"] == pytest.approx(2000.0)
        assert 0 < zone["strength"] <= 1
        assert len(result["demand"]) <= 3
        assert len(result["supply"]) <= 3


class TestLiquidityTool:
    async def test_a_raid_that_closes_back_inside_is_a_sweep(
        self, db_session: AsyncSession
    ) -> None:
        series = flat_bars(65, price=2000.0, spread=0.5, interval=timedelta(minutes=15))
        series.append(
            OHLCBar(
                ts=series[-1].ts + timedelta(minutes=15),
                open=2000.0,
                high=2001.5,  # through the prior extreme...
                low=1999.8,
                close=2000.2,  # ...and back inside: a sweep, not a break.
                volume=0.0,
            )
        )
        await _seed_series(db_session, Timeframe.M15, series)

        result = await dispatch_tool(
            ToolContext(session=db_session), "get_liquidity", {"timeframe": "M15"}
        )
        assert result["recent_sweep"] is not None
        assert result["recent_sweep"]["side"] == "BUY_SIDE"
        assert result["recent_sweep"]["level"] == pytest.approx(2000.5)
        # Tolerance derives from gold's pip size, not an FX constant.
        assert result["tolerance"] == pytest.approx(0.02)
        assert isinstance(result["equal_highs"], list)
        assert isinstance(result["equal_lows"], list)


class TestVolatilityTool:
    async def test_reports_atr_and_a_classification(self, db_session: AsyncSession) -> None:
        await _seed_series(db_session, Timeframe.M15, _uptrend(Timeframe.M15))
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_volatility_regime", {"timeframe": "M15"}
        )
        assert result["atr"] > 0
        assert result["bucket"] in {"LOW", "MEDIUM", "HIGH"}
        assert result["regime"] in {"RANGING", "TRENDING"}

    async def test_too_few_bars_reads_unknown_not_a_guess(self, db_session: AsyncSession) -> None:
        await _seed_series(db_session, Timeframe.M5, _uptrend(Timeframe.M5)[:10])
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_volatility_regime", {"timeframe": "M5"}
        )
        assert result["regime"] == "UNKNOWN"
        assert result["atr"] is None


class TestMtfBiasTool:
    async def test_reads_the_h4_h1_m15_ladder(self, db_session: AsyncSession) -> None:
        for frame in (Timeframe.H4, Timeframe.H1, Timeframe.M15):
            await _seed_series(db_session, frame, _uptrend(frame))
        result = await dispatch_tool(ToolContext(session=db_session), "get_mtf_bias", {})
        assert result["stack"] == ["H4", "H1", "M15"]
        assert result["alignment"] == "FULL_BULLISH"
        assert result["trade_bias"] == "BULLISH"
        assert result["conflict"] is False
        # The three constitutional roles are named, not implied.
        assert result["roles"]["leads"] == "H4"
        assert result["roles"]["times_entry"] == "M15"

    async def test_the_decision_frame_joins_the_ladder(self, db_session: AsyncSession) -> None:
        for frame in (Timeframe.H4, Timeframe.H1, Timeframe.M15):
            await _seed_series(db_session, frame, _uptrend(frame))
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_mtf_bias", {"timeframe": "M1"}
        )
        assert result["decision_timeframe"] == "M1"
        # Unseeded M1 is a data fact, reported as UNKNOWN rather than NEUTRAL.
        assert result["biases"]["M1"] == "UNKNOWN"

    async def test_an_empty_store_declines_rather_than_guessing(
        self, db_session: AsyncSession
    ) -> None:
        result = await dispatch_tool(ToolContext(session=db_session), "get_mtf_bias", {})
        assert result["status"] == "unavailable"
        assert result["reason"] == "INSUFFICIENT_DATA"


class TestPriceContextTool:
    async def test_the_floor_is_measured_from_the_tape(self, db_session: AsyncSession) -> None:
        await _seed_series(db_session, Timeframe.M15, _uptrend(Timeframe.M15))
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_price_context", {"timeframe": "M15"}
        )
        assert result["noise"] > 0
        assert result["atr"] > 0
        assert result["bars"] == 50  # the noise window, not the whole series
        assert result["last_close"] > 0
        assert result["usable"] is True

    async def test_spread_is_never_invented(self, db_session: AsyncSession) -> None:
        """D12: no live quote reaches this path, so no spread may appear on it."""
        await _seed_series(db_session, Timeframe.M15, _uptrend(Timeframe.M15))
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_price_context", {"timeframe": "M15"}
        )
        assert result["observed_spread"] is None


class TestTimeframeReadTool:
    async def test_names_the_frame_and_why_the_others_lost(self, db_session: AsyncSession) -> None:
        await _seed_series(db_session, Timeframe.M15, _uptrend(Timeframe.M15))
        result = await dispatch_tool(ToolContext(session=db_session), "get_timeframe_read", {})
        assert result["timeframe"] == "M15"
        assert result["rationale"]
        by_frame = {c["timeframe"]: c for c in result["candidates"]}
        assert set(by_frame) == {"M1", "M5", "M15"}
        assert by_frame["M1"]["excluded"] == "INSUFFICIENT_BARS"
        assert by_frame["M5"]["excluded"] == "INSUFFICIENT_BARS"
        assert by_frame["M15"]["excluded"] is None
        assert by_frame["M15"]["reasons"]

    async def test_no_viable_frame_is_an_answer_not_a_default(
        self, db_session: AsyncSession
    ) -> None:
        """An empty store must not produce a confident choice about any chart."""
        result = await dispatch_tool(ToolContext(session=db_session), "get_timeframe_read", {})
        assert result["error"] == "NoViableTimeframeError"
        assert "M1=INSUFFICIENT_BARS" in result["detail"]


class TestNewsTool:
    async def test_newest_first_and_limited(self, db_session: AsyncSession) -> None:
        await _seed_news(db_session, count=5)
        result = await dispatch_tool(ToolContext(session=db_session), "get_news", {"limit": 2})
        assert result["count"] == 2
        assert result["items"][0]["published_at"] > result["items"][1]["published_at"]
        assert result["items"][0]["headline"]

    async def test_the_limit_is_capped_at_one_hundred(self, db_session: AsyncSession) -> None:
        """A tool call must not be able to pull the whole news table into a prompt."""
        await _seed_news(db_session, count=105)
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_news", {"limit": 100_000}
        )
        assert result["count"] == 100

    async def test_a_nonsense_limit_is_clamped_not_erred(self, db_session: AsyncSession) -> None:
        await _seed_news(db_session, count=3)
        result = await dispatch_tool(ToolContext(session=db_session), "get_news", {"limit": -50})
        assert result["count"] == 1

    async def test_currency_filter_is_case_insensitive(self, db_session: AsyncSession) -> None:
        await _seed_news(db_session, count=2, currency="USD")
        await _seed_news(db_session, count=2, currency="EUR")
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_news", {"currency": "usd"}
        )
        assert result["count"] == 2
        assert all(item["currency"] == "USD" for item in result["items"])

    async def test_news_needs_no_workspace_binding(self, db_session: AsyncSession) -> None:
        """``news_events`` is deliberately platform-global (shared market fact),
        so the tool is platform-scoped and answers on an unbound context —
        unlike workspace tools, which dispatch refuses without a tenant."""
        await _seed_news(db_session, count=1)
        result = await dispatch_tool(ToolContext(session=db_session, tenant=None), "get_news", {})
        assert result["count"] == 1

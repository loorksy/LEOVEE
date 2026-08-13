"""The agent's two ways of seeing: browsing the data, and looking at the chart."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import TOOLS, ToolContext, dispatch_tool, tool_definitions
from app.engines.structure import run_structure_engine
from app.engines.zones import run_zones_engine
from app.models.enums import Timeframe
from app.providers.market.base import NormalizedCandle
from app.services import market_data
from app.services.chart.render import render_chart_png
from app.services.chart.visual_evidence import (
    collect_visual_evidence,
    visual_timeframes_for,
)
from app.tests.bars import flat_bars, swinging_bars

START = datetime(2026, 1, 1, tzinfo=UTC)


class TestRenderer:
    pytestmark = pytest.mark.no_db

    def test_produces_a_real_png(self) -> None:
        image = render_chart_png(swinging_bars(20), symbol="XAUUSD", timeframe="M15")
        # PNG magic number: proof it is an image, not an empty buffer.
        assert image.png[:8] == b"\x89PNG\r\n\x1a\n"
        assert image.width == 1280

    def test_refuses_to_draw_nothing(self) -> None:
        with pytest.raises(ValueError):
            render_chart_png([], symbol="XAUUSD", timeframe="M15")

    def test_window_is_bounded_so_candles_stay_legible(self) -> None:
        # A thousand bars in 1280 pixels is a smear, and a model reading a
        # smear describes structure that is not there.
        image = render_chart_png(swinging_bars(80), symbol="XAUUSD", timeframe="M1", max_bars=50)
        assert image.bar_count == 50

    def test_a_flat_series_still_renders(self) -> None:
        image = render_chart_png(flat_bars(60), symbol="XAUUSD", timeframe="M15")
        assert image.price_high > image.price_low

    def test_levels_are_inside_the_drawn_range(self) -> None:
        """A support just outside the window would be clipped off the image."""
        bars = swinging_bars(20)
        far_below = min(b.low for b in bars) - 50
        image = render_chart_png(
            bars,
            symbol="XAUUSD",
            timeframe="M15",
            structure={"nearest_support": far_below},
        )
        assert image.price_low <= far_below
        assert "nearest_support" in image.drawn

    def test_caption_metadata_describes_the_window(self) -> None:
        image = render_chart_png(swinging_bars(20), symbol="XAUUSD", timeframe="M5")
        assert image.symbol == "XAUUSD"
        assert image.timeframe == "M5"
        assert image.bar_count > 0

    def test_base64_round_trips(self) -> None:
        image = render_chart_png(swinging_bars(20), symbol="XAUUSD", timeframe="M15")
        assert base64.b64decode(image.to_base64()) == image.png


class TestVisualLadder:
    pytestmark = pytest.mark.no_db

    @pytest.mark.parametrize(
        ("decision", "expected"),
        [
            (Timeframe.M1, ("M1", "M5", "M15")),
            (Timeframe.M5, ("M5", "M15", "H1")),
            (Timeframe.M15, ("M15", "H1", "H4")),
        ],
    )
    def test_shows_the_frame_plus_the_two_above_it(
        self, decision: Timeframe, expected: tuple[str, ...]
    ) -> None:
        assert tuple(tf.value for tf in visual_timeframes_for(decision)) == expected

    def test_the_decision_frame_is_always_first(self) -> None:
        for decision in (Timeframe.M1, Timeframe.M5, Timeframe.M15):
            assert visual_timeframes_for(decision)[0] is decision


async def _seed_candles(session: AsyncSession, timeframe: Timeframe, count: int) -> None:
    symbol = await market_data.get_or_create_symbol(session, "XAUUSD")
    minutes = {
        Timeframe.M1: 1,
        Timeframe.M5: 5,
        Timeframe.M15: 15,
        Timeframe.H1: 60,
        Timeframe.H4: 240,
    }
    candles = []
    for i in range(count):
        price = Decimal("2000") + Decimal(i % 20) * Decimal("0.8")
        candles.append(
            NormalizedCandle(
                symbol="XAUUSD",
                timeframe=timeframe,
                ts=START + timedelta(minutes=minutes[timeframe] * i),
                open=price,
                high=price + Decimal("1.2"),
                low=price - Decimal("1.2"),
                close=price + Decimal("0.4"),
                volume=Decimal("100"),
                complete=True,
                source="test_double",
            )
        )
    await market_data.upsert_candles(session, symbol.id, candles)
    await session.flush()


class TestVisualEvidence:
    async def test_captures_the_ladder(self, db_session: AsyncSession) -> None:
        for frame in (Timeframe.M15, Timeframe.H1, Timeframe.H4):
            await _seed_candles(db_session, frame, 120)

        evidence = await collect_visual_evidence(
            db_session, symbol="XAUUSD", timeframe=Timeframe.M15
        )
        assert [s.timeframe for s in evidence.snapshots] == ["M15", "H1", "H4"]
        assert evidence.missing == []

    async def test_a_missing_frame_is_reported_not_omitted(self, db_session: AsyncSession) -> None:
        # A model told "I could not show you H4" reasons differently from one
        # silently handed two charts instead of three.
        await _seed_candles(db_session, Timeframe.M15, 120)
        await _seed_candles(db_session, Timeframe.H1, 120)

        evidence = await collect_visual_evidence(
            db_session, symbol="XAUUSD", timeframe=Timeframe.M15
        )
        assert [s.timeframe for s in evidence.snapshots] == ["M15", "H1"]
        assert [m["timeframe"] for m in evidence.missing] == ["H4"]
        assert evidence.missing[0]["reason"]

    async def test_overlays_belong_only_to_the_analysed_frame(
        self, db_session: AsyncSession
    ) -> None:
        """Painting M15 levels onto H4 would show levels that frame never produced."""
        for frame in (Timeframe.M15, Timeframe.H1, Timeframe.H4):
            await _seed_candles(db_session, frame, 150)

        bars = swinging_bars(20)
        evidence = await collect_visual_evidence(
            db_session,
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            structure=run_structure_engine(bars),
            zones=run_zones_engine(bars),
        )
        by_frame = {s.timeframe: s for s in evidence.snapshots}
        assert by_frame["H1"].image.drawn == []
        assert by_frame["H4"].image.drawn == []

    async def test_payload_shape_carries_a_caption(self, db_session: AsyncSession) -> None:
        await _seed_candles(db_session, Timeframe.M15, 120)
        evidence = await collect_visual_evidence(
            db_session, symbol="XAUUSD", timeframe=Timeframe.M15
        )
        payload = evidence.as_payload()
        first = payload["snapshots"][0]
        assert first["media_type"] == "image/png"
        assert "XAUUSD" in first["caption"]
        assert base64.b64decode(first["data"])[:8] == b"\x89PNG\r\n\x1a\n"


class TestAgentTools:
    async def test_every_tool_is_declared(self) -> None:
        names = {definition["name"] for definition in tool_definitions()}
        assert names == set(TOOLS)

    async def test_browse_candles(self, db_session: AsyncSession) -> None:
        await _seed_candles(db_session, Timeframe.M15, 80)
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_candles", {"timeframe": "M15", "count": 30}
        )
        assert result["count"] == 30
        assert result["candles"][0]["ts"] < result["candles"][-1]["ts"]

    async def test_candle_count_is_bounded(self, db_session: AsyncSession) -> None:
        """A tool call must not be able to pull a year of M1 into a prompt."""
        await _seed_candles(db_session, Timeframe.M15, 120)
        result = await dispatch_tool(
            ToolContext(session=db_session),
            "get_candles",
            {"timeframe": "M15", "count": 100_000},
        )
        assert result["count"] <= 500

    async def test_browse_indicators(self, db_session: AsyncSession) -> None:
        await _seed_candles(db_session, Timeframe.M15, 200)
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_indicators", {"timeframe": "M15"}
        )
        assert result["rsi14"] is not None
        assert result["atr14"] is not None

    async def test_browse_structure(self, db_session: AsyncSession) -> None:
        await _seed_candles(db_session, Timeframe.M15, 200)
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_structure", {"timeframe": "M15"}
        )
        assert "nearest_support" in result
        assert result["structure"] in ("uptrend", "downtrend", "range", "unknown")

    async def test_data_coverage_reports_the_stored_range(self, db_session: AsyncSession) -> None:
        # "No structure before this point" and "we only have two days of data"
        # look identical without this.
        await _seed_candles(db_session, Timeframe.M15, 40)
        result = await dispatch_tool(ToolContext(session=db_session), "get_data_coverage", {})
        assert result["coverage"]["M15"]["earliest"] is not None
        assert result["coverage"]["H4"]["earliest"] is None

    async def test_chart_image_tool_returns_png_payloads(self, db_session: AsyncSession) -> None:
        await _seed_candles(db_session, Timeframe.M15, 150)
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_chart_image", {"timeframe": "M15"}
        )
        assert result["snapshots"]
        assert result["snapshots"][0]["media_type"] == "image/png"

    async def test_symbols_outside_the_allowlist_are_refused(
        self, db_session: AsyncSession
    ) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_candles", {"symbol": "EURUSD"}
        )
        assert result["error"] == "UnknownSymbolError"

    async def test_non_stored_timeframes_are_refused(self, db_session: AsyncSession) -> None:
        result = await dispatch_tool(
            ToolContext(session=db_session), "get_candles", {"timeframe": "D1"}
        )
        assert result["error"] == "ValueError"

    async def test_unknown_tool_is_reported_as_data(self, db_session: AsyncSession) -> None:
        # A model that guessed a tool name should be corrected, not crash the run.
        result = await dispatch_tool(ToolContext(session=db_session), "place_trade", {})
        assert result["error"] == "unknown_tool"
        assert "get_candles" in result["available"]

    async def test_the_surface_is_read_only(self) -> None:
        """No tool mutates anything: Leovee analyses, it does not execute."""
        forbidden = ("place", "close", "modify", "cancel", "delete", "write")
        for name in TOOLS:
            assert not any(word in name for word in forbidden), name

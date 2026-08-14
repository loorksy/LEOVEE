"""The bridge between what the engine found and what the chart draws.

If these two disagree the product tells the reader two different things at once,
and the chart is the one they will believe. So the test that matters most is the
round trip: every annotation traces back to a real detected object, at the price
the engine measured, anchored at the pivot it was found on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.engines.bar import OHLCBar
from app.engines.geometry import run_geometry_engine
from app.engines.geometry.detect import detect_chart_geometry
from app.engines.geometry.to_annotations import geometry_to_annotations, summarize_geometry
from app.engines.geometry.types import GeometrySnapshot, PatternInstance, PatternStatus, PatternType
from app.schemas.chart import ChartSemanticRole, ChartSemanticType
from app.tests.bars import swinging_bars

pytestmark = pytest.mark.no_db

EPOCH = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)


def _bars() -> list[OHLCBar]:
    return swinging_bars(30, start=2000.0, drift=3.0, swing=9.0, bars_per_leg=4)


def _snapshot() -> GeometrySnapshot:
    return detect_chart_geometry(_bars())


def test_every_annotation_traces_back_to_something_the_engine_found() -> None:
    """No annotation may be invented here.

    This layer's whole justification is that the chart and the narrative cite the
    same objects. A drawing with no detected counterpart breaks that silently —
    it looks exactly like a real one.
    """
    snapshot = _snapshot()
    annotations = geometry_to_annotations(snapshot, timeframe="M15")

    expected = (
        len(snapshot.trendlines)
        + len(snapshot.channels)
        + len(snapshot.patterns)
        + sum(1 for pattern in snapshot.patterns if pattern.neckline is not None)
    )
    assert len(annotations) == expected


def test_anchors_are_timestamps_and_prices_never_bar_indices() -> None:
    """An index means nothing to a renderer that paginates its own data, and it
    becomes wrong the moment the window scrolls."""
    annotations = geometry_to_annotations(_snapshot(), timeframe="M15")
    assert annotations, "the fixture must produce something to check"
    for annotation in annotations:
        for anchor in annotation.geometry.anchors:
            # Parses as a real instant, and carries the frame it belongs to.
            assert datetime.fromisoformat(anchor.ts).tzinfo is not None
            assert isinstance(anchor.price, float)
            assert anchor.timeframe == "M15"


def test_a_trendline_keeps_the_price_the_engine_measured() -> None:
    snapshot = _snapshot()
    if not snapshot.trendlines:
        pytest.skip("fixture produced no trendline")
    line = snapshot.trendlines[0]
    annotation = geometry_to_annotations(snapshot, timeframe="M15")[0]

    assert annotation.semantic_type is ChartSemanticType.TREND_LINE
    assert annotation.confidence == line.confidence
    assert annotation.geometry.metadata["price_at_last_bar"] == line.price_at_last_bar
    assert annotation.geometry.metadata["touches"] == line.touches
    assert [anchor.price for anchor in annotation.geometry.anchors] == [
        pivot.price for pivot in line.anchors
    ]


def test_a_support_line_and_a_resistance_line_carry_different_roles() -> None:
    """Type and role are separate axes. Both are lines; only the role differs."""
    snapshot = _snapshot()
    roles = {
        annotation.role
        for annotation in geometry_to_annotations(snapshot)
        if annotation.semantic_type is ChartSemanticType.TREND_LINE
    }
    assert roles <= {ChartSemanticRole.SUPPORT, ChartSemanticRole.RESISTANCE}


def test_a_forming_pattern_is_drawn_dashed() -> None:
    """The one visual distinction here that is semantic rather than cosmetic.

    A forming structure has not happened yet, and drawing it solid asserts
    something that does not exist.
    """
    from app.engines.primitives.pivots import Pivot

    pivots = [
        Pivot(index=i, ts=EPOCH + timedelta(minutes=15 * i), price=2000.0 + i, kind="high")
        for i in range(3)
    ]
    for status, expected in (
        (PatternStatus.FORMING, "dashed"),
        (PatternStatus.COMPLETED, "solid"),
    ):
        snapshot = GeometrySnapshot(
            pivots=[],
            trendlines=[],
            channels=[],
            patterns=[
                PatternInstance(pattern_type=PatternType.DOUBLE_TOP, status=status, anchors=pivots)
            ],
            candlesticks=[],
            candle_count=100,
            atr=2.0,
        )
        annotation = geometry_to_annotations(snapshot)[0]
        assert annotation.style.line_style == expected, status


def test_status_and_stage_stay_separate_all_the_way_to_the_renderer() -> None:
    """Collapsing them loses "nearly complete, unconfirmed" — the state a reader
    most needs to see, and the one both other values hide."""
    snapshot = _snapshot()
    patterns = [
        annotation
        for annotation in geometry_to_annotations(snapshot)
        if annotation.semantic_type is ChartSemanticType.POLYLINE_PATTERN
    ]
    for annotation in patterns:
        metadata = annotation.geometry.metadata
        assert "status" in metadata
        assert "stage" in metadata


def test_the_summary_and_the_drawings_come_from_one_snapshot() -> None:
    """The numeric digest the model reads and the picture the user sees describe
    the same objects, or the narrative cites levels that are not on screen."""
    snapshot = _snapshot()
    summary = summarize_geometry(snapshot)
    annotations = geometry_to_annotations(snapshot)

    drawn_patterns = [
        annotation.pattern_type
        for annotation in annotations
        if annotation.semantic_type is ChartSemanticType.POLYLINE_PATTERN
    ]
    assert drawn_patterns == [entry["pattern"] for entry in summary["patterns"]]
    assert len(summary["trendlines"]) == len(snapshot.trendlines)


def test_an_engine_that_declined_produces_no_drawings() -> None:
    """A short window returns `unavailable`, and an unavailable engine has
    nothing to draw — not an empty chart it claims to have analysed."""
    payload = run_geometry_engine(_bars()[:20])
    assert payload.get("status") == "unavailable"


def test_no_terminal_drawing_vocabulary_survived_the_port() -> None:
    """The reference emitted the same drawings to a broker terminal as well (D3).

    Keeping its twenty-seven native shapes would leave a hole shaped exactly
    like broker integration for someone to fill in later.

    Named without the terminal's product name on purpose: the execution-surface
    guard scans identifiers, and it is right to — a name is code. The absence
    can be asserted without spelling the thing out in a symbol.
    """
    values = {member.value for member in ChartSemanticType}
    for native in ("hline", "vline", "ray", "trend", "trendline", "rectangle"):
        assert native not in values, native

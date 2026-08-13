"""The geometry engine: templates, state machine, and the bounded-output contract.

These are *intent* tests, reproduced from AiChart's own geometry suite. They pin
shapes rather than numbers: a double top is two highs at one level with a trough
between, and the assertion says exactly that. A test written against the
confidence figure a detector happens to produce pins the arithmetic instead, and
then any genuine improvement to the scoring reads as a regression.

Every fixture is built by naming its turning prices, so the shape under test is
legible in the test itself (see ``app/tests/bars.path_bars``).
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.engines.bar import OHLCBar
from app.engines.geometry.candlesticks import detect_candlesticks
from app.engines.geometry.channels import MAX_CHANNELS, detect_channels
from app.engines.geometry.detect import (
    GEOMETRY_MIN_CONFIDENCE,
    MAX_PATTERNS,
    detect_chart_geometry,
)
from app.engines.geometry.pattern_stage import (
    expected_anchors_for,
    offers_anticipatory_entry,
)
from app.engines.geometry.pattern_state import first_close_beyond, project_measured_move
from app.engines.geometry.trendlines import MAX_LINES_PER_SIDE
from app.engines.geometry.types import PatternStage, PatternStatus, PatternType
from app.engines.primitives.pivots import geometry_atr
from app.tests.bars import EPOCH, bar, flat_bars, path_bars, rising_bars

pytestmark = pytest.mark.no_db

# --- fixtures, named by the shape they draw ---------------------------------

#: Two highs at ~2000 with a trough at 1988, then a close below the trough.
DOUBLE_TOP = [1975, 1982, 1974, 1980, 1972, 2000, 1988, 2000.4, 1978, 1974]
#: Shoulder 1995, head 2015, shoulder 1996, then a break through the neckline.
HEAD_SHOULDERS = [1972, 1978, 1970, 1995, 1985, 2015, 1984, 1996, 1965, 1962]
#: Flat highs at 2000, lows climbing 1980 → 1988 → 1993. Still inside.
ASCENDING_TRIANGLE = [1968, 1974, 1966, 2000, 1980, 2000, 1988, 2000, 1993, 2000]


def _rising_channel() -> list[float]:
    turns: list[float] = []
    for i in range(6):
        turns.append(1960.0 + 5 * i)
        turns.append(1975.0 + 5 * i)
    return turns


def _bars(turns: Sequence[float], bars_per_leg: int = 8) -> list[OHLCBar]:
    return path_bars(turns, bars_per_leg=bars_per_leg)


# --- the bounded-output contract --------------------------------------------


def test_snapshot_respects_every_documented_bound() -> None:
    """The bounds are the contract, not a performance measure.

    Bounded output is what keeps a snapshot usable as model context and as a
    drawing: a chart carrying forty overlapping claims tells a reader less than
    one carrying three.
    """
    snapshot = detect_chart_geometry(_bars(_rising_channel(), bars_per_leg=7))

    for side in ("support", "resistance"):
        assert (
            len([line for line in snapshot.trendlines if line.side == side]) <= MAX_LINES_PER_SIDE
        )
    assert len(snapshot.channels) <= MAX_CHANNELS
    assert len(snapshot.patterns) <= MAX_PATTERNS
    assert all(line.confidence >= GEOMETRY_MIN_CONFIDENCE for line in snapshot.trendlines)
    assert all(p.confidence >= GEOMETRY_MIN_CONFIDENCE for p in snapshot.patterns)


def test_window_is_capped_at_the_analysis_window() -> None:
    snapshot = detect_chart_geometry(rising_bars(900))
    assert snapshot.candle_count == 500


def test_detection_is_deterministic() -> None:
    """Same candles, byte-identical snapshot.

    The snapshot feeds the decision, the drawn chart and the model's numeric
    context. If it varied between calls those three would disagree about the
    same market, and nothing downstream could tell which one was wrong.
    """
    bars = _bars(DOUBLE_TOP)
    first = detect_chart_geometry(bars).to_dict()
    for _ in range(50):
        assert detect_chart_geometry(bars).to_dict() == first


def test_too_few_candles_returns_an_empty_snapshot() -> None:
    snapshot = detect_chart_geometry(rising_bars(40))
    assert snapshot.patterns == []
    assert snapshot.trendlines == []
    assert snapshot.atr == 0.0


def test_zero_volatility_returns_an_empty_snapshot() -> None:
    """With no volatility scale every threshold would compare a price to zero."""
    motionless = [
        bar(ts=EPOCH, open=2000.0, high=2000.0, low=2000.0, close=2000.0) for _ in range(120)
    ]
    snapshot = detect_chart_geometry(motionless)
    assert snapshot.atr == 0.0
    assert snapshot.patterns == []
    assert snapshot.candlesticks == []


# --- reversal templates ------------------------------------------------------


def test_double_top_is_detected_and_projects_downward() -> None:
    snapshot = detect_chart_geometry(_bars(DOUBLE_TOP))
    pattern = next(p for p in snapshot.patterns if p.pattern_type is PatternType.DOUBLE_TOP)

    assert pattern.break_direction == "down"
    assert pattern.neckline is not None
    assert pattern.projected_target is not None
    assert pattern.break_level is not None
    assert pattern.projected_target < pattern.break_level


def test_head_and_shoulders_is_detected_with_five_anchors() -> None:
    snapshot = detect_chart_geometry(_bars(HEAD_SHOULDERS))
    pattern = next(p for p in snapshot.patterns if p.pattern_type is PatternType.HEAD_AND_SHOULDERS)

    assert len(pattern.anchors) == 5
    # Head above both shoulders is the whole template.
    shoulder_a, _, head, _, shoulder_b = pattern.anchors
    assert head.price > shoulder_a.price
    assert head.price > shoulder_b.price
    assert pattern.break_direction == "down"


def test_a_completed_break_with_follow_through_reads_as_confirmed() -> None:
    """`confirmed` must be reachable, or the stage axis carries no information.

    The reference implementation computed the break bar inside each detector and
    then dropped it, so the confirmation check — which looks at the bars *after*
    the break — had nothing to look after and every completion stayed
    `completed_unconfirmed` forever. Carrying `break_index` is the fix, and this
    is the test that would have caught it.
    """
    snapshot = detect_chart_geometry(_bars(DOUBLE_TOP))
    pattern = next(p for p in snapshot.patterns if p.pattern_type is PatternType.DOUBLE_TOP)

    assert pattern.status is PatternStatus.COMPLETED
    assert pattern.break_index is not None
    assert pattern.stage is PatternStage.CONFIRMED
    assert pattern.completion_ratio == 1.0


# --- converging boundaries ---------------------------------------------------


def test_ascending_triangle_is_detected_while_still_forming() -> None:
    snapshot = detect_chart_geometry(_bars(ASCENDING_TRIANGLE))
    pattern = next(p for p in snapshot.patterns if p.pattern_type is PatternType.ASCENDING_TRIANGLE)

    assert pattern.status is PatternStatus.FORMING
    assert pattern.break_direction == "up"
    assert len(pattern.anchors) == 4


def test_a_forming_pattern_pressing_its_boundary_is_near_completion() -> None:
    """ "Not complete" must not read as "nothing here".

    The boundary of a nearly finished structure is often the best entry
    available; collapsing it into the same bucket as a shape two bars old is the
    exact confusion the stage axis exists to remove.
    """
    snapshot = detect_chart_geometry(_bars(ASCENDING_TRIANGLE))
    pattern = next(p for p in snapshot.patterns if p.pattern_type is PatternType.ASCENDING_TRIANGLE)

    assert pattern.stage is PatternStage.NEAR_COMPLETION
    assert offers_anticipatory_entry(pattern.stage)


def test_channel_is_a_parallel_offset_of_its_base_line() -> None:
    snapshot = detect_chart_geometry(_bars(_rising_channel(), bars_per_leg=7))
    assert len(snapshot.channels) == 1
    channel = snapshot.channels[0]

    assert channel.direction == "rising"
    assert channel.opposite_touches >= 2
    assert 1.0 <= channel.width_atr <= 8.0
    # Parallel by construction: both boundaries share the base anchors' bars.
    assert [p.index for p in channel.parallel] == [p.index for p in channel.base.anchors]


def test_channel_needs_two_opposite_touches() -> None:
    bars = _bars(_rising_channel(), bars_per_leg=7)
    atr = geometry_atr(bars)
    trendlines = detect_chart_geometry(bars).trendlines
    assert detect_channels([], trendlines, atr) == []


# --- the shared state machine ------------------------------------------------


def test_a_wick_through_a_level_does_not_complete_a_pattern() -> None:
    """A wick through a level is a sweep, not a break.

    Price reached for the orders resting there and was rejected. Treating it as
    a completion is how a detector reports a head-and-shoulders break on the
    exact bar that proved the neckline held.
    """
    bars = [bar(ts=EPOCH, open=2000.0, high=2001.0, low=1999.0, close=2000.0) for _ in range(10)]
    # A deep wick below 1990, closing back at 2000.
    bars.append(bar(open=2000.0, high=2001.0, low=1980.0, close=2000.0))

    swept = first_close_beyond(bars, 5, lambda _i: 1990.0, "down", atr=1.0)
    assert swept.broken is False

    bars.append(bar(open=2000.0, high=2000.5, low=1985.0, close=1986.0))
    closed = first_close_beyond(bars, 5, lambda _i: 1990.0, "down", atr=1.0)
    assert closed.broken is True
    assert closed.break_index == len(bars) - 1


def test_measured_move_projects_the_height_from_the_break() -> None:
    assert project_measured_move(1990.0, 12.0, "down") == pytest.approx(1978.0)
    assert project_measured_move(1990.0, 12.0, "up") == pytest.approx(2002.0)
    # Sign of the height never flips the direction.
    assert project_measured_move(1990.0, -12.0, "down") == pytest.approx(1978.0)


@pytest.mark.parametrize(
    ("pattern_type", "expected"),
    [
        ("head_and_shoulders", 5),
        ("inverse_head_and_shoulders", 5),
        ("triple_top", 5),
        ("double_bottom", 4),
        ("ascending_triangle", 4),
        ("wedge", 4),
        ("rectangle", 4),
        ("cup_and_handle", 4),
        ("bull_flag", 3),
    ],
)
def test_expected_anchor_counts_match_each_template(pattern_type: str, expected: int) -> None:
    assert expected_anchors_for(pattern_type) == expected


# --- candlestick shapes ------------------------------------------------------


def _tail(*bars: OHLCBar) -> list[OHLCBar]:
    """Twelve quiet bars, then the shapes under test on a known volatility scale."""
    lead = [bar(ts=EPOCH, open=2000.0, high=2001.0, low=1999.0, close=2000.0) for _ in range(12)]
    return lead + list(bars)


def test_doji_is_named_by_a_body_inside_a_fraction_of_atr() -> None:
    bars = _tail(bar(open=2000.0, high=2002.0, low=1998.0, close=2000.02))
    names = {s.name for s in detect_candlesticks(bars, atr=2.0)}
    assert "doji" in names


def test_bullish_engulfing_needs_the_prior_body_swallowed() -> None:
    bars = _tail(
        bar(open=2000.0, high=2000.5, low=1997.0, close=1997.5),
        bar(open=1997.0, high=2002.0, low=1996.5, close=2001.5),
    )
    signals = detect_candlesticks(bars, atr=2.0)
    engulfing = next(s for s in signals if s.name == "bullish_engulfing")
    assert engulfing.direction == "bullish"
    assert engulfing.span_bars == 2


def test_the_same_shape_is_a_hammer_or_a_hanging_man_by_the_prior_move() -> None:
    """Context is part of the *name*, not a judgement layered on top of it.

    A long lower shadow after a decline is a hammer; the identical bar after a
    rally is a hanging man. Without the prior move the detector cannot name
    either one correctly, and calling both "long lower wick" throws the meaning
    away.
    """

    def shape() -> OHLCBar:
        return bar(open=2000.0, high=2000.6, low=1994.0, close=2000.4)

    down = [
        bar(open=2020.0 - 4 * i, high=2021.0 - 4 * i, low=2019.0 - 4 * i, close=2019.5 - 4 * i)
        for i in range(12)
    ]
    down.append(shape())
    assert "hammer" in {s.name for s in detect_candlesticks(down, atr=2.0)}

    up = [
        bar(open=1980.0 + 4 * i, high=1981.0 + 4 * i, low=1979.0 + 4 * i, close=1980.5 + 4 * i)
        for i in range(12)
    ]
    up.append(shape())
    assert "hanging_man" in {s.name for s in detect_candlesticks(up, atr=2.0)}


def test_candlestick_signals_are_most_recent_first_and_bounded() -> None:
    signals = detect_candlesticks(flat_bars(120, price=2000.0, spread=2.0), atr=1.0, limit=5)
    assert len(signals) <= 5
    assert [s.index for s in signals] == sorted((s.index for s in signals), reverse=True)


def test_candlesticks_need_a_volatility_scale() -> None:
    assert detect_candlesticks(rising_bars(50), atr=0.0) == []

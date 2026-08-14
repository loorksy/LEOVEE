"""Multi-timeframe alignment: measured from bars, and honest about conflict."""

from __future__ import annotations

import pytest

from app.engines.bar import OHLCBar
from app.engines.mtf import run_mtf_engine
from app.engines.status import is_unavailable
from app.tests.bars import path_bars, swinging_bars

pytestmark = pytest.mark.no_db

STACK = ("H4", "H1", "M15")


def _uptrend(bars: int = 90) -> list[OHLCBar]:
    return swinging_bars(bars // 8 or 2, drift=6.0, swing=9.0, bars_per_leg=4)


def _downtrend(bars: int = 90) -> list[OHLCBar]:
    return swinging_bars(bars // 8 or 2, drift=-6.0, swing=9.0, bars_per_leg=4)


def _range(cycles: int = 10) -> list[OHLCBar]:
    turns: list[float] = []
    for _ in range(cycles):
        turns.extend([2000.0, 2012.0])
    return path_bars(turns, bars_per_leg=5)


def test_aligned_frames_report_full_alignment() -> None:
    mtf = run_mtf_engine(
        {"H4": _uptrend(), "H1": _uptrend(), "M15": _uptrend()},
        decision_timeframe="M15",
        stack=STACK,
    )
    assert mtf["alignment"] == "FULL_BULLISH"
    assert mtf["trade_bias"] == "BULLISH"
    assert mtf["conflict"] is False


def test_a_scalp_against_the_leading_frame_is_reported_as_a_conflict() -> None:
    """The mistake this engine exists to catch.

    Selling a 15-minute bounce inside a strong H4 uptrend is a specific and
    expensive error: the pullback being sold is the trend's entry. Counting
    votes would call this "mixed" and move on.
    """
    mtf = run_mtf_engine(
        {"H4": _uptrend(), "H1": _uptrend(), "M15": _downtrend()},
        decision_timeframe="M15",
        stack=STACK,
    )
    assert mtf["conflict"] is True
    # The trade bias follows the leading context frame, not the fast one.
    assert mtf["trade_bias"] == "BULLISH"
    assert mtf["biases"]["M15"] == "BEARISH"


def test_the_three_roles_are_named() -> None:
    """The constitution requires the answer to say which frame does what."""
    mtf = run_mtf_engine(
        {"H4": _uptrend(), "H1": _range(), "M15": _uptrend()},
        decision_timeframe="M15",
        stack=STACK,
    )
    roles = mtf["roles"]
    assert roles["leads"] == "H4"
    assert roles["times_entry"] == "M15"
    assert "H4" not in roles["context"]


def test_the_leader_is_the_slowest_frame_that_says_something() -> None:
    """A ranging H4 does not lead; it abstains, and H1 leads instead."""
    mtf = run_mtf_engine(
        {"H4": _range(), "H1": _downtrend(), "M15": _downtrend()},
        decision_timeframe="M15",
        stack=STACK,
    )
    assert mtf["roles"]["leads"] == "H1"
    assert mtf["trade_bias"] == "BEARISH"


def test_a_thin_frame_is_unknown_rather_than_neutral() -> None:
    """Too few bars is a data fact, not a market fact."""
    mtf = run_mtf_engine(
        {"H4": _uptrend(), "H1": swinging_bars(2, bars_per_leg=2), "M15": _uptrend()},
        decision_timeframe="M15",
        stack=STACK,
    )
    assert mtf["biases"]["H1"] == "UNKNOWN"
    # An unreadable frame must not count as a vote either way.
    assert mtf["alignment"] == "FULL_BULLISH"


def test_no_readable_frame_declines_rather_than_reporting_neutral() -> None:
    mtf = run_mtf_engine({"H4": [], "H1": [], "M15": []}, decision_timeframe="M15", stack=STACK)
    assert is_unavailable(mtf)
    assert mtf["detail"] == "NO_READABLE_FRAME"


def test_no_frames_at_all_declines() -> None:
    assert is_unavailable(run_mtf_engine({}))

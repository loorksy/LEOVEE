"""Differential test: forward outcomes against the TypeScript they came from.

The resolution of a case is the memory's *answer*. If it drifts, the platform
still retrieves the right past moments and then reports the wrong thing about
what happened next — which is worse than retrieving the wrong moments, because
the retrieval looks correct.

One field diverges by decision, not by accident: `net_r` no longer carries an
execution cost (ADR 0010). The test asserts the divergence is exactly that and
nothing more.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.engines.bar import OHLCBar
from app.services.memory.cases.outcome import (
    MIN_STATS_SAMPLE,
    CaseResolution,
    ForwardOutcome,
    resolve_forward_outcome,
    summarize_outcomes,
)

pytestmark = pytest.mark.no_db

_GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "golden" / "case_outcome.json").read_text()
)
_SERIES = {entry["id"]: entry["future"] for entry in _GOLDEN["series"]}
_EPOCH = datetime(2026, 6, 10, tzinfo=UTC)
_TOL = 1e-9


def _bars(candles: list[dict[str, Any]]) -> list[OHLCBar]:
    return [
        OHLCBar(
            ts=_EPOCH + timedelta(minutes=15 * index),
            open=candle["open"],
            high=candle["high"],
            low=candle["low"],
            close=candle["close"],
        )
        for index, candle in enumerate(candles)
    ]


def _outcome(payload: dict[str, Any]) -> ForwardOutcome:
    return ForwardOutcome(
        resolution=CaseResolution(payload["resolution"]),
        bars=payload["bars"],
        max_favourable_atr=payload["maxFavourableAtr"],
        max_adverse_atr=payload["maxAdverseAtr"],
        net_r=payload["netR"],
    )


@pytest.mark.parametrize(
    "case",
    _GOLDEN["resolutions"],
    ids=lambda c: f"{c['id']}-{c['direction']}-h{c['horizon']}",
)
def test_resolution_matches_the_reference(case: dict[str, Any]) -> None:
    kwargs: dict[str, Any] = {
        "direction": case["direction"],
        "entry": case["entry"],
        "atr": case["atr"],
        "future": _bars(_SERIES[case["id"]]),
    }
    if case["horizon"] is not None:
        kwargs["horizon"] = case["horizon"]

    result = resolve_forward_outcome(**kwargs)
    want = case["output"]

    # Exact on the discrete answer: which way it went and how long it took. A
    # port that lands in the wrong branch still produces plausible excursions.
    assert result.resolution.value == want["resolution"]
    assert result.bars == want["bars"]
    assert result.max_favourable_atr == pytest.approx(want["maxFavourableAtr"], rel=_TOL, abs=_TOL)
    assert result.max_adverse_atr == pytest.approx(want["maxAdverseAtr"], rel=_TOL, abs=_TOL)
    # With no cost charged, the reference's own arithmetic reduces to these —
    # so this is still an equality with the reference, not an exemption from it.
    assert result.net_r == pytest.approx(want["netR"], rel=_TOL, abs=_TOL)


@pytest.mark.parametrize("index", range(len(_GOLDEN["summaries"])))
def test_summary_matches_the_reference(index: int) -> None:
    case = _GOLDEN["summaries"][index]
    stats = summarize_outcomes([_outcome(o) for o in case["outcomes"]])
    want = case["output"]

    assert stats.sample_size == want["sampleSize"]
    assert stats.target_first == want["targetFirst"]
    assert stats.stop_first == want["stopFirst"]
    assert stats.unresolved == want["unresolved"]

    for got, expected in (
        (stats.hit_rate, want["hitRate"]),
        (stats.average_net_r, want["averageNetR"]),
        (stats.average_bars, want["averageBars"]),
    ):
        # None is a value here, not a missing one: it means "the sample cannot
        # support this figure". Approx-comparing it away would erase the
        # distinction the whole minimum-sample rule exists to draw.
        if expected is None:
            assert got is None
        else:
            assert got == pytest.approx(expected, rel=_TOL, abs=_TOL)


def test_a_bar_touching_both_levels_resolves_as_the_stop() -> None:
    """From OHLC alone the order inside a bar is unknowable.

    Resolving toward the target would inflate every hit rate this memory
    reports, and it would do so silently and always in the same direction.
    """
    entry, atr = 2000.0, 2.0
    both = OHLCBar(ts=_EPOCH, open=entry, high=entry + 3 * atr, low=entry - 2 * atr, close=entry)
    for direction in ("buy", "sell"):
        result = resolve_forward_outcome(direction=direction, entry=entry, atr=atr, future=[both])
        assert result.resolution is CaseResolution.STOP_FIRST
        assert result.bars == 1


def test_a_short_future_is_unresolved_not_missing() -> None:
    """A case with twelve forward bars gets an answer: it did not resolve.

    Reported with `bars` equal to what was actually walked, so a case that ran
    out of history is distinguishable from one that ran the full horizon.
    """
    result = resolve_forward_outcome(
        direction="buy", entry=2000.0, atr=2.0, future=_bars(_SERIES["short_future_12_bars"])
    )
    assert result.resolution is CaseResolution.UNRESOLVED
    assert result.bars == 12
    assert result.net_r == 0.0


def test_no_future_at_all_is_still_an_answer() -> None:
    result = resolve_forward_outcome(direction="buy", entry=2000.0, atr=2.0, future=[])
    assert result.resolution is CaseResolution.UNRESOLVED
    assert result.bars == 0


def test_rates_are_withheld_below_the_sample_floor() -> None:
    """ "Three of four worked" invites a conclusion the data cannot support."""
    wins = [
        ForwardOutcome(CaseResolution.TARGET_FIRST, 5, 2.1, 0.3, 2.0)
        for _ in range(MIN_STATS_SAMPLE - 1)
    ]
    thin = summarize_outcomes(wins)
    assert thin.sample_size == MIN_STATS_SAMPLE - 1
    assert thin.target_first == MIN_STATS_SAMPLE - 1
    assert thin.hit_rate is None
    assert thin.sufficient is False

    enough = summarize_outcomes([*wins, wins[0]])
    assert enough.sufficient is True
    assert enough.hit_rate == 1.0


def test_unresolved_cases_do_not_count_against_the_hit_rate() -> None:
    """An unresolved case is not a loss — it is a case that never answered.

    Putting it in the denominator would report an edge as weaker the more often
    it simply ran out of time, which is a fact about the horizon, not the edge.
    """
    outcomes = [
        *[ForwardOutcome(CaseResolution.TARGET_FIRST, 5, 2.1, 0.3, 2.0) for _ in range(3)],
        *[ForwardOutcome(CaseResolution.STOP_FIRST, 4, 0.5, 1.1, -1.0) for _ in range(1)],
        *[ForwardOutcome(CaseResolution.UNRESOLVED, 40, 1.0, 0.9, 0.0) for _ in range(6)],
    ]
    stats = summarize_outcomes(outcomes)
    assert stats.hit_rate == pytest.approx(0.75)
    # ...but they do dilute the average return, which is exactly what they cost.
    assert stats.average_net_r == pytest.approx(0.5)


def test_a_sample_that_never_resolved_reports_no_hit_rate() -> None:
    """Ten cases, none of which answered, is not a 0% hit rate."""
    stats = summarize_outcomes(
        [ForwardOutcome(CaseResolution.UNRESOLVED, 40, 1.0, 0.9, 0.0) for _ in range(10)]
    )
    assert stats.sufficient is True
    assert stats.hit_rate is None
    assert stats.average_net_r == 0.0

"""Differential test: the fingerprint against the TypeScript it was ported from.

Fingerprints are the memory's index. If a ported feature drifts by a rounding
step, the platform does not fail — it retrieves slightly the wrong past cases,
computes a confidence from them, and presents it with exactly the same
authority. That is why this is a fixture comparison and not a reading.

One field is allowed to diverge, and the test says which and why: see
`RECENT_ATR_PERIOD` in the module under test. Every other field is exact.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.engines.bar import OHLCBar
from app.services.memory.cases.fingerprint import (
    CaseFingerprint,
    fingerprint_at,
    fingerprint_similarity,
    fingerprint_vector,
)

pytestmark = pytest.mark.no_db

_GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "golden" / "case_fingerprint.json").read_text()
)

_TOL = 1e-9


def _bars(candles: list[dict[str, Any]]) -> list[OHLCBar]:
    return [
        OHLCBar(
            ts=datetime.fromtimestamp(candle["time"] / 1000, tz=UTC),
            open=candle["open"],
            high=candle["high"],
            low=candle["low"],
            close=candle["close"],
        )
        for candle in candles
    ]


def _from_reference(payload: dict[str, Any]) -> CaseFingerprint:
    return CaseFingerprint(
        regime=payload["regime"],
        trend=payload["trend"],
        range_zone=payload["rangeZone"],
        pullback_depth=payload["pullbackDepth"],
        impulse_atr=payload["impulseAtr"],
        volatility=payload["volatility"],
        session=payload["session"],
        structure_run=payload["structureRun"],
    )


@pytest.mark.parametrize("case", _GOLDEN["fingerprints"], ids=lambda c: str(c["id"]))
def test_fingerprint_matches_the_reference(case: dict[str, Any]) -> None:
    result = fingerprint_at(_bars(case["candles"]))
    want = case["fingerprint"]

    if want is None:
        # Refusal is a result. A window too short must produce nothing rather
        # than a fingerprint over a range that does not exist.
        assert result is None
        return

    assert result is not None
    # Categorical fields exactly: a wrong zone or trend is not a small error,
    # it files the case under a different past entirely.
    assert result.trend == want["trend"]
    assert result.range_zone == want["rangeZone"]
    assert result.session == want["session"]
    assert result.structure_run == want["structureRun"]

    assert result.pullback_depth == pytest.approx(want["pullbackDepth"], rel=_TOL, abs=_TOL)
    assert result.impulse_atr == pytest.approx(want["impulseAtr"], rel=_TOL, abs=_TOL)
    assert result.volatility == pytest.approx(want["volatility"], rel=_TOL, abs=_TOL)

    # `regime` is the single permitted divergence, and only in one direction:
    # the port may say `volatile` where the reference could not. Anything else
    # is a porting bug wearing the exception's clothes.
    if result.regime != want["regime"]:
        assert result.regime == "volatile", (result.regime, want["regime"])


def test_the_reference_could_never_report_a_volatile_regime() -> None:
    """The finding the divergence exists for, pinned rather than asserted in prose.

    `recentAtr = atrOf(candles.slice(-15), 14)` and `atr = atrOf(candles)` read
    the same fifteen bars, so the ratio was always exactly 1.0. The fixture set
    includes a series whose last twelve bars carry a sixfold volatility burst,
    and even that comes back `trend`.
    """
    regimes = {
        case["fingerprint"]["regime"]
        for case in _GOLDEN["fingerprints"]
        if case["fingerprint"] is not None
    }
    assert "volatile" not in regimes
    burst = next(case for case in _GOLDEN["fingerprints"] if case["id"] == "volatility_burst")
    assert burst["fingerprint"]["_volatilityRatio"] == 1.0


@pytest.mark.parametrize(
    "case",
    _GOLDEN["vectors"],
    ids=lambda c: f"{c['fingerprint']['regime']}-{c['fingerprint']['trend']}",
)
def test_the_vector_slots_match_the_reference(case: dict[str, Any]) -> None:
    """Slot order and the clamps. The order is persisted, so it is frozen."""
    vector = fingerprint_vector(_from_reference(case["fingerprint"]))
    assert len(vector) == 8
    for got, want in zip(vector, case["vector"], strict=True):
        assert got == pytest.approx(want, rel=_TOL, abs=_TOL)


@pytest.mark.parametrize("index", range(len(_GOLDEN["similarities"])))
def test_similarity_matches_the_reference(index: int) -> None:
    case = _GOLDEN["similarities"][index]
    got = fingerprint_similarity(_from_reference(case["a"]), _from_reference(case["b"]))
    assert got == pytest.approx(case["similarity"], rel=_TOL, abs=_TOL)


def test_a_fingerprint_is_perfectly_similar_to_itself() -> None:
    fingerprint = _from_reference(
        next(c["fingerprint"] for c in _GOLDEN["fingerprints"] if c["fingerprint"])
    )
    assert fingerprint_similarity(fingerprint, fingerprint) == 1.0


def test_a_trend_disagreement_costs_more_than_a_session_disagreement() -> None:
    """The whole reason the metric is weighted rather than plain L1."""
    base = CaseFingerprint("trend", "up", "mid", 0.5, 2.0, 0.001, "london", 3)
    other_session = CaseFingerprint("trend", "up", "mid", 0.5, 2.0, 0.001, "asia", 3)
    other_trend = CaseFingerprint("trend", "down", "mid", 0.5, 2.0, 0.001, "london", 3)
    assert fingerprint_similarity(base, other_session) > fingerprint_similarity(base, other_trend)


def test_a_window_that_ends_later_is_a_different_moment() -> None:
    """The lookahead guard, stated as a property.

    Nothing enforces at runtime that a caller passed a window ending where the
    case sits — the function cannot know. What it *can* guarantee is that it
    reads only the bars it was given, so appending one future bar changes the
    answer rather than being ignored.
    """
    candles = next(c for c in _GOLDEN["fingerprints"] if c["id"] == "uptrend_london")["candles"]
    bars = _bars(candles)
    assert fingerprint_at(bars[:-1]) != fingerprint_at(bars)


def test_the_corrected_regime_branch_actually_fires() -> None:
    """A three-valued classifier that can only ever say two things.

    The first repair attempt — a genuinely shorter ATR period against the
    original — left `volatile` just as unreachable, because the two windows
    overlap almost entirely and the ratio stays pinned near 1. This asserts the
    branch is live, on the same burst series the reference reads as `trend`, so
    it cannot quietly die again the next time someone adjusts a window.
    """
    burst = next(case for case in _GOLDEN["fingerprints"] if case["id"] == "volatility_burst")
    assert burst["fingerprint"]["regime"] == "trend"

    result = fingerprint_at(_bars(burst["candles"]))
    assert result is not None
    assert result.regime == "volatile"


def test_an_ordinary_tape_is_not_called_volatile() -> None:
    """The other half: a live branch that fires on everything is no better.

    Every non-burst series in the fixture set must keep the regime the reference
    gave it, or the correction has traded a silent classifier for a noisy one.
    """
    for case in _GOLDEN["fingerprints"]:
        if case["fingerprint"] is None or case["id"] == "volatility_burst":
            continue
        result = fingerprint_at(_bars(case["candles"]))
        assert result is not None
        assert result.regime == case["fingerprint"]["regime"], case["id"]

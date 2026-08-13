"""The stage graph, the failure taxonomy, and the timeframe selector."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.agents.errors import (
    AgentStage,
    FailureCode,
    StageFailure,
    classify_error,
    ledger_silent_timeout,
    stage_failure_from_error,
)
from app.agents.pipeline import PipelineLedger, run_stage, run_stages_concurrently
from app.agents.timeframe import (
    NoViableTimeframeError,
    select_decision_timeframe,
)
from app.engines.bar import OHLCBar
from app.models.enums import Timeframe
from app.tests.bars import flat_bars, rising_bars, swinging_bars

pytestmark = pytest.mark.no_db


# --- the taxonomy ------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("HTTP 401 unauthorized", FailureCode.AUTH),
        ("invalid api key supplied", FailureCode.AUTH),
        ("HTTP 429 rate limit exceeded", FailureCode.RATE_LIMIT),
        ("HTTP 400 bad request: unsupported parameter", FailureCode.PROVIDER_BAD_REQUEST),
        ("model does not exist", FailureCode.PROVIDER_BAD_REQUEST),
        ("HTTP 503 overloaded", FailureCode.PROVIDER_UNAVAILABLE),
        ("request timed out", FailureCode.TIMEOUT),
        ("connection reset by peer", FailureCode.NETWORK),
        ("candles are stale", FailureCode.STALE_DATA),
        ("insufficient candles for analysis", FailureCode.INSUFFICIENT_DATA),
        ("OANDA_TOKEN not configured", FailureCode.CONFIGURATION),
        ("something nobody predicted", FailureCode.UNKNOWN),
    ],
)
def test_errors_are_classified_by_cause(message: str, expected: FailureCode) -> None:
    code, _ = classify_error(message)
    assert code is expected


def test_billing_exhaustion_is_not_a_rate_limit() -> None:
    """It arrives as the same 429, and "try again shortly" is wrong forever.

    Matched before the rate-limit branch precisely because they share a status
    code — the ordering of those two branches is the whole rule.
    """
    code, _ = classify_error("HTTP 429: you exceeded your current quota, check billing")
    assert code is FailureCode.PROVIDER_BILLING
    assert stage_failure_from_error(AgentStage.FINAL_DECISION, "billing").retryable is False


def test_a_retryable_failure_is_marked_as_such() -> None:
    assert stage_failure_from_error(AgentStage.NEWS, "HTTP 503 unavailable").retryable is True
    assert stage_failure_from_error(AgentStage.NEWS, "HTTP 401").retryable is False


def test_operator_detail_is_bounded() -> None:
    """A log line, not a payload dump: an unbounded provider message carries the
    whole request back into the trace."""
    failure = stage_failure_from_error(AgentStage.GENERAL, "x" * 5_000)
    assert len(failure.operator_detail) == 500


# --- the ledger --------------------------------------------------------------


async def test_a_successful_stage_records_its_value_and_duration() -> None:
    ledger = PipelineLedger()

    async def work() -> str:
        return "done"

    result = await run_stage(ledger, AgentStage.STRUCTURE, work)
    assert result.ok
    assert ledger.value(AgentStage.STRUCTURE) == "done"
    assert ledger.failures == []


async def test_a_raising_stage_is_classified_and_does_not_end_the_run() -> None:
    ledger = PipelineLedger()

    async def work() -> str:
        raise RuntimeError("HTTP 503 overloaded")

    result = await run_stage(ledger, AgentStage.NEWS, work)
    assert result.ok is False
    assert result.failure is not None
    assert result.failure.code is FailureCode.PROVIDER_UNAVAILABLE
    assert ledger.failed_stages() == ["news"]


async def test_a_hung_stage_hits_its_deadline_and_the_run_continues() -> None:
    ledger = PipelineLedger()

    async def work() -> str:
        await asyncio.sleep(5)
        return "never"

    result = await run_stage(ledger, AgentStage.LIQUIDITY, work, deadline_seconds=0.05)
    assert result.failure is not None
    assert result.failure.code is FailureCode.TIMEOUT


def test_a_silent_deadline_is_ledgered_from_the_absence_of_a_value() -> None:
    """The subtlest failure in the pipeline.

    A stage run under a timeout that resolves to a fallback rather than raising
    leaves no exception behind, so a run whose specialists all timed out reports
    itself healthy with every stage quietly empty. An empty value with no
    recorded failure can only mean the deadline hit.
    """
    failures: list[StageFailure] = []
    ledger_silent_timeout(failures, AgentStage.STRUCTURE, None, 5.0)
    assert failures[0].code is FailureCode.TIMEOUT

    # A value present, or a failure already recorded, must not add a second one.
    ledger_silent_timeout(failures, AgentStage.LIQUIDITY, "value", 5.0)
    ledger_silent_timeout(failures, AgentStage.STRUCTURE, None, 5.0)
    assert len(failures) == 1


async def test_cancellation_is_recorded_and_still_propagates() -> None:
    """A cancelled run is a deliberate stop: worth recording, never worth
    swallowing."""
    ledger = PipelineLedger()

    async def work() -> str:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_stage(ledger, AgentStage.GEOMETRY, work)
    assert ledger.failures[0].code is FailureCode.CANCELLED


async def test_independent_specialists_run_concurrently() -> None:
    """In sequence they multiply the slowest provider by five for no benefit."""

    async def slow() -> str:
        await asyncio.sleep(0.1)
        return "ok"

    ledger = PipelineLedger()
    started = asyncio.get_running_loop().time()
    results = await run_stages_concurrently(
        ledger,
        {
            AgentStage.STRUCTURE: slow,
            AgentStage.LIQUIDITY: slow,
            AgentStage.SUPPLY_DEMAND: slow,
            AgentStage.GEOMETRY: slow,
        },
    )
    elapsed = asyncio.get_running_loop().time() - started
    assert all(r.ok for r in results.values())
    assert elapsed < 0.3, "stages ran in sequence"


async def test_one_failing_specialist_does_not_take_the_others_down() -> None:
    async def ok() -> str:
        return "ok"

    async def boom() -> str:
        raise RuntimeError("HTTP 500")

    ledger = PipelineLedger()
    results = await run_stages_concurrently(
        ledger, {AgentStage.STRUCTURE: ok, AgentStage.LIQUIDITY: boom}
    )
    assert results[AgentStage.STRUCTURE].ok
    assert results[AgentStage.LIQUIDITY].ok is False
    assert ledger.failed_stages() == ["liquidity"]


# --- timeframe selection -----------------------------------------------------


#: London, the baseline session (multiplier 1.0), so the cost floor in these
#: tests is a fixed number rather than whatever session the suite happens to run
#: in. That the selector needs this at all is the point of
#: `test_selection_does_not_read_the_clock`.
LONDON = datetime(2026, 6, 10, 9, tzinfo=UTC)


#: ATRs chosen to clear the London cost floor, so these fixtures exercise
#: *selection* rather than the exclusion tested separately below.
def _frames(**overrides: object) -> dict[str, list[OHLCBar]]:
    base = {
        "M1": swinging_bars(18, drift=1.2, swing=3.5, bars_per_leg=4),
        "M5": swinging_bars(18, drift=2.0, swing=6.0, bars_per_leg=4),
        "M15": swinging_bars(18, drift=3.0, swing=9.0, bars_per_leg=4),
    }
    return {**base, **overrides}  # type: ignore[dict-item]


def test_a_frame_is_chosen_and_the_reasoning_is_reported() -> None:
    choice = select_decision_timeframe(_frames(), moment=LONDON)
    assert choice.timeframe in (Timeframe.M1, Timeframe.M5, Timeframe.M15)
    assert choice.rationale
    assert len(choice.candidates) == 3


def test_an_unreadable_frame_is_excluded_not_merely_scored_low() -> None:
    """A frame with no structure cannot carry a plan however good it looks
    otherwise, so it is not allowed to win on volatility."""
    choice = select_decision_timeframe(
        _frames(M15=rising_bars(200, start=2000.0, step=0.5, spread=0.4)), moment=LONDON
    )
    by_tf = {c.timeframe: c for c in choice.candidates}
    assert by_tf[Timeframe.M15].excluded == "NO_READABLE_STRUCTURE"
    assert choice.timeframe is not Timeframe.M15


def test_a_frame_with_no_room_after_costs_is_excluded() -> None:
    """Not "worse" — impossible. No plan on it can ever be viable.

    This is the check that makes the platform refuse a structurally losing
    trade rather than rank it below a better one and take it anyway when the
    better one is unavailable.
    """
    quiet = swinging_bars(18, drift=0.02, swing=0.06, bars_per_leg=4)
    choice = select_decision_timeframe(_frames(M1=quiet), moment=LONDON)
    by_tf = {c.timeframe: c for c in choice.candidates}
    assert by_tf[Timeframe.M1].excluded == "NO_ROOM_AFTER_COSTS"
    assert by_tf[Timeframe.M1].reasons  # says by how much it fell short


def test_a_thin_frame_is_excluded_for_want_of_bars() -> None:
    choice = select_decision_timeframe(_frames(M1=swinging_bars(2, bars_per_leg=2)), moment=LONDON)
    by_tf = {c.timeframe: c for c in choice.candidates}
    assert by_tf[Timeframe.M1].excluded == "INSUFFICIENT_BARS"


def test_agreement_with_the_context_frame_is_a_bonus_not_a_filter() -> None:
    """Trading against the higher frame is a real setup; it just has to earn it."""
    aligned = select_decision_timeframe(_frames(), leading_bias="BULLISH", moment=LONDON)
    against = select_decision_timeframe(_frames(), leading_bias="BEARISH", moment=LONDON)
    aligned_best = max(c.score for c in aligned.candidates if c.excluded is None)
    against_best = max(c.score for c in against.candidates if c.excluded is None)
    assert aligned_best > against_best
    # Still a choice either way — the conflict does not veto the run.
    assert against.timeframe is not None


def test_no_viable_frame_raises_rather_than_defaulting() -> None:
    """A default here is a confident answer about a chart the agent has just
    established it cannot read."""
    dead = {tf: flat_bars(120, price=2000.0, spread=0.001) for tf in ("M1", "M5", "M15")}
    with pytest.raises(NoViableTimeframeError, match="no scalping frame"):
        select_decision_timeframe(dead, moment=LONDON)


def test_a_quiet_gold_tape_excludes_the_fastest_frames_on_cost_alone() -> None:
    """The finding this check exists to surface, pinned so it cannot drift.

    Gold's modelled retail spread is 30 pips (0.30 USD). With slippage charged
    on both sides that is a 64-pip round trip, so the 3x floor demands a first
    target of 1.92 USD — which on M1, at a stop of 0.8xATR and a first target of
    1.2R, needs an ATR of 2.00 USD. Ordinary one-minute gold runs far below
    that.

    So on a normal tape the platform declines to scalp gold on M1, and that is
    the correct answer rather than a miscalibration: at those costs the
    arithmetic never closes, whatever the win rate. The frame comes back into
    play when a real observed spread replaces the conservative model.
    """
    ordinary = {
        "M1": swinging_bars(18, drift=0.15, swing=0.5, bars_per_leg=4),
        "M5": swinging_bars(18, drift=0.4, swing=1.2, bars_per_leg=4),
        "M15": swinging_bars(18, drift=3.0, swing=9.0, bars_per_leg=4),
    }
    choice = select_decision_timeframe(ordinary, moment=LONDON)
    by_tf = {c.timeframe: c for c in choice.candidates}
    assert by_tf[Timeframe.M1].excluded == "NO_ROOM_AFTER_COSTS"
    assert choice.timeframe is Timeframe.M15


def test_selection_is_deterministic() -> None:
    frames = _frames()
    first = select_decision_timeframe(frames, moment=LONDON).to_dict()
    for _ in range(10):
        assert select_decision_timeframe(frames, moment=LONDON).to_dict() == first


def test_selection_does_not_read_the_clock() -> None:
    """Spread is session-shaped, so the cost floor moves between Asia and the
    overlap. Reading `now()` would return different frames for identical candles
    depending on when the run happened, with nothing in the output saying why —
    and replaying the analysis would not reproduce it.
    """
    frames = _frames()
    asia = select_decision_timeframe(frames, moment=datetime(2026, 6, 10, 2, tzinfo=UTC))
    overlap = select_decision_timeframe(frames, moment=datetime(2026, 6, 10, 14, tzinfo=UTC))
    asia_best = max(c.score for c in asia.candidates if c.excluded is None)
    overlap_best = max(c.score for c in overlap.candidates if c.excluded is None)
    # Thinner books in Asia mean less headroom past the cost floor.
    assert overlap_best > asia_best


def test_a_tighter_observed_spread_brings_a_fast_frame_back() -> None:
    """The exclusion is about costs, not about the frame itself."""
    ordinary = {
        "M1": swinging_bars(18, drift=0.5, swing=1.6, bars_per_leg=4),
        "M5": swinging_bars(18, drift=0.6, swing=1.8, bars_per_leg=4),
        "M15": swinging_bars(18, drift=0.7, swing=2.0, bars_per_leg=4),
    }
    modelled = select_decision_timeframe(ordinary, moment=LONDON)
    observed = select_decision_timeframe(ordinary, moment=LONDON, observed_spread_pips=4.0)
    excluded_modelled = {c.timeframe for c in modelled.candidates if c.excluded}
    excluded_observed = {c.timeframe for c in observed.candidates if c.excluded}
    assert excluded_observed < excluded_modelled

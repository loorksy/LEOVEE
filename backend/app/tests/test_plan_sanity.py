"""Plan sanity: does the plan survive the market it was written for?

Not execution logic. Every check here is about whether the *recommendation* is
sound, which matters identically on a platform that never sends an order.

These tests used to be written against a modelled retail spread — a session
table, a static gold constant, a round-trip cost floor. That model is gone, and
so are its tests: nothing here asserts on a number that was not measured off the
candles.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

import pytest

from app.engines.bar import OHLCBar
from app.engines.plan_sanity import (
    MIN_STOP_NOISE_MULTIPLE,
    NOISE_WINDOW_BARS,
    PriceContext,
    measure_price_context,
    reward_risk,
    risk_policy_for,
    run_plan_sanity_engine,
)
from app.engines.primitives.pivots import geometry_atr
from app.models.enums import Timeframe

pytestmark = pytest.mark.no_db

_START = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)


def _bar(index: int, *, close_at: float, body: float, wick: float) -> OHLCBar:
    """A bar whose wick — the part of the range price gave back — is exactly ``wick``."""
    open_ = close_at - body
    return OHLCBar(
        ts=_START + timedelta(minutes=index),
        open=open_,
        high=max(open_, close_at) + wick / 2,
        low=min(open_, close_at) - wick / 2,
        close=close_at,
    )


def _tape(*, wick: float = 0.6, body: float = 0.4, bars: int = 60) -> list[OHLCBar]:
    return [_bar(i, close_at=2000.0 + i * 0.01, body=body, wick=wick) for i in range(bars)]


def _context(**overrides: Any) -> PriceContext:
    kwargs: dict[str, Any] = {"atr": 5.0}
    kwargs.update(overrides)
    bars = kwargs.pop("bars", None)
    return measure_price_context(_tape() if bars is None else bars, **kwargs)


def _plan(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "entry": 2000.0,
        "stop": 1996.0,
        "targets": [2008.0],
        "context": _context(),
    }
    return {**base, **overrides}


# --- the plan checks --------------------------------------------------------


def test_a_sound_scalp_plan_passes() -> None:
    result = run_plan_sanity_engine(**_plan())
    assert result["viable"] is True
    assert result["failures"] == []
    assert result["warnings"] == []
    assert result["reward_risk"] == pytest.approx(2.0)
    # Gold pips are 0.01, so a 4.00 stop is 400 of them.
    assert result["stop_distance_pips"] == pytest.approx(400.0)


def test_a_stop_inside_the_measured_noise_is_fatal() -> None:
    """Swept by one ordinary probe, not by the thesis being wrong.

    The floor is the median wick on this tape — 0.60 — so a 0.30 stop is inside
    movement these very candles show price giving back and getting back.
    """
    result = run_plan_sanity_engine(**_plan(stop=1999.7))
    assert result["viable"] is False
    assert "STOP_INSIDE_NOISE" in result["failures"]
    assert result["required_stop_distance"] == pytest.approx(0.6 * MIN_STOP_NOISE_MULTIPLE)
    assert result["stop_noise_multiple"] == pytest.approx(0.5)


def test_a_target_inside_a_single_bars_movement_is_fatal() -> None:
    """A coin flip on noise, not a read of the market.

    Half an ATR is the floor: below it the target sits inside what the next
    candle does anyway, so reaching it says nothing about the analysis.
    """
    result = run_plan_sanity_engine(**_plan(targets=[2000.5]))
    assert result["viable"] is False
    assert "TARGET_INSIDE_NOISE" in result["failures"]
    assert result["first_target_atr"] == pytest.approx(0.1)


def test_a_zero_distance_stop_is_unpriceable_not_merely_wide() -> None:
    result = run_plan_sanity_engine(**_plan(stop=2000.0))
    assert result["viable"] is False
    assert result["failures"] == ["STOP_DISTANCE_ZERO"]
    assert result["reward_risk"] is None


def test_a_missing_target_fails_rather_than_defaulting() -> None:
    result = run_plan_sanity_engine(**_plan(targets=[]))
    assert result["viable"] is False
    assert "NO_TARGET" in result["failures"]


def test_an_unmeasurable_tape_declines_to_judge_rather_than_approving() -> None:
    """No floor means the check did not run — which is not the same as passing.

    Returning ``viable`` on a missing measurement turns "we could not tell" into
    a blanket approval, which is exactly the class of lie this engine exists to
    stop telling.
    """
    result = run_plan_sanity_engine(**_plan(context=measure_price_context([], atr=5.0)))
    assert result["viable"] is False
    assert "NO_PRICE_CONTEXT" in result["failures"]


def test_reward_risk_below_one_warns_and_is_never_silent() -> None:
    result = run_plan_sanity_engine(**_plan(stop=1990.0, targets=[2005.0]))
    assert "REWARD_RISK_BELOW_ONE" in result["warnings"]
    assert result["viable"] is True


# --- spread: reported, never a gate -----------------------------------------


def test_a_wide_live_spread_warns_and_nothing_more() -> None:
    """A fact about this instant. A plan is not unviable because of one print."""
    result = run_plan_sanity_engine(**_plan(context=_context(observed_spread=2.0)))
    assert "SPREAD_WIDE_RIGHT_NOW" in result["warnings"]
    assert result["viable"] is True
    assert result["context"]["observed_spread"] == pytest.approx(2.0)


def test_no_quote_means_no_spread_claim_at_all() -> None:
    """The old engine substituted a modelled number here and gated on it.

    Now an absent quote is simply absent: nothing is invented to fill the hole,
    and nothing downstream is decided by the hole's contents.
    """
    result = run_plan_sanity_engine(**_plan())
    assert result["context"]["observed_spread"] is None
    assert result["warnings"] == []
    assert result["viable"] is True


# --- the measurement itself -------------------------------------------------


def test_the_floor_is_the_wick_not_the_range() -> None:
    """The distinction the first attempt at this check got wrong.

    Median bar range *is* ATR under another name, so a stop sized as a fraction
    of ATR could never clear a multiple of it — the check rejected every scalp
    for arithmetic reasons rather than market ones.
    """
    bars = _tape(wick=0.6, body=0.4)
    context = measure_price_context(bars, atr=5.0)
    assert context.noise == pytest.approx(0.6)
    assert context.noise < median(bar.range for bar in bars)


def test_one_violent_candle_does_not_set_the_floor_for_the_rest() -> None:
    """The median, not the mean: otherwise every stop after payrolls looks generous."""
    bars = _tape(wick=0.6, body=0.4)
    bars[-1] = _bar(len(bars) - 1, close_at=2000.6, body=0.4, wick=40.0)
    context = measure_price_context(bars, atr=5.0)
    assert context.noise == pytest.approx(0.6)


def test_the_floor_describes_the_session_being_traded_not_the_whole_history() -> None:
    calm = _tape(wick=0.2, body=0.1, bars=NOISE_WINDOW_BARS)
    stale = _tape(wick=9.0, body=0.1, bars=200)
    context = measure_price_context(stale + calm, atr=5.0)
    assert context.bars == NOISE_WINDOW_BARS
    assert context.noise == pytest.approx(0.2)


def test_a_flat_tape_is_unusable_rather_than_infinitely_permissive() -> None:
    flat = [
        OHLCBar(
            ts=_START + timedelta(minutes=i),
            open=2000.0,
            high=2000.0,
            low=2000.0,
            close=2000.0,
        )
        for i in range(60)
    ]
    context = measure_price_context(flat, atr=5.0)
    assert context.noise == 0.0
    assert context.usable is False


def test_an_ordinary_tape_leaves_a_frame_policy_stop_room_to_breathe() -> None:
    """The regression this whole rewrite exists for.

    Under the previous floor no decision frame could pass on an ordinary tape:
    the stop was a fraction of ATR and the floor was a multiple of the median
    range, so the arithmetic closed against every scalp before the market was
    consulted. On a plain random walk, each frame's own stop must clear the
    noise its own candles show.
    """
    rng = random.Random(20260610)
    price = 2000.0
    bars: list[OHLCBar] = []
    for i in range(300):
        drift = rng.gauss(0.0, 0.5)
        open_ = price
        price = open_ + drift
        top = max(open_, price) + abs(rng.gauss(0.0, 0.2))
        bottom = min(open_, price) - abs(rng.gauss(0.0, 0.2))
        bars.append(
            OHLCBar(ts=_START + timedelta(minutes=i), open=open_, high=top, low=bottom, close=price)
        )

    atr = geometry_atr(bars)
    context = measure_price_context(bars, atr=atr)
    for timeframe in (Timeframe.M1, Timeframe.M5, Timeframe.M15):
        policy = risk_policy_for(timeframe)
        stop_distance = atr * policy.stop_atr_multiple
        entry = bars[-1].close
        result = run_plan_sanity_engine(
            entry=entry,
            stop=entry - stop_distance,
            targets=[entry + stop_distance * policy.target_r[0]],
            context=context,
        )
        assert result["viable"] is True, (timeframe.value, result["failures"])


def test_reward_risk_is_computed_from_the_levels_not_asserted() -> None:
    assert reward_risk(2000.0, 1990.0, 2020.0) == pytest.approx(2.0)
    assert reward_risk(2000.0, 2000.0, 2020.0) is None
    assert reward_risk(2000.0, 1990.0, None) is None


# --- the per-frame policy ---------------------------------------------------


def test_faster_frames_get_tighter_stops_and_shorter_holds() -> None:
    """A scalp is not a slow trade in miniature."""
    fast = risk_policy_for(Timeframe.M1)
    slow = risk_policy_for(Timeframe.M15)
    assert fast.stop_atr_multiple < slow.stop_atr_multiple
    assert fast.maximum_holding_bars < slow.maximum_holding_bars
    assert fast.target_r[0] < fast.target_r[1]


def test_a_non_decision_frame_has_no_policy() -> None:
    """H1 is context. There is no plan geometry for a frame we never trade."""
    with pytest.raises(ValueError, match="not a decision timeframe"):
        risk_policy_for(Timeframe.H1)

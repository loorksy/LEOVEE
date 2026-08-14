"""An edge does not stop working all at once — and noise is not decay.

The policy under test is pure, which is the point: whether a strategy is
demoted is a judgement worth being able to read in one file, with no database
and no clock in it.

The asymmetry is the design and most of these tests are about it. A downgrade is
immediate; an upgrade has to be earned twice. Getting that backwards in either
direction has a cost: demote slowly and the reader keeps acting on a dead edge,
promote quickly and one lucky result revives a broken one.
"""

from __future__ import annotations

import pytest

from app.services.strategies.decay_lifecycle import (
    DEFAULT_DECAY_THRESHOLDS,
    DecayReason,
    LifecycleState,
    LivePerformance,
    evaluate_lifecycle,
)

pytestmark = pytest.mark.no_db

_N = DEFAULT_DECAY_THRESHOLDS.min_sample_for_judgement


def _live(
    win_rate: float, *, sample: int = _N, pf: float | None = 2.0, mean_r: float | None = None
) -> LivePerformance:
    return LivePerformance(sample_size=sample, win_rate=win_rate, profit_factor=pf, mean_r=mean_r)


def test_a_healthy_strategy_stays_active() -> None:
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE, live=_live(0.60), baseline_win_rate=0.62
    )
    assert result.state is LifecycleState.ACTIVE
    assert result.reason is DecayReason.HEALTHY
    assert result.usable_as_support is True


def test_a_thin_window_holds_the_state_rather_than_demoting() -> None:
    """Noise is not decay.

    A strategy that had a bad fortnight has had a bad fortnight. Demoting on it
    means the label tracks variance, and a label that tracks variance is one the
    reader learns to ignore.
    """
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE,
        live=_live(0.10, sample=_N - 1),
        baseline_win_rate=0.62,
    )
    assert result.state is LifecycleState.ACTIVE
    assert result.reason is DecayReason.INSUFFICIENT_SAMPLE


def test_a_moderate_shortfall_starts_monitoring() -> None:
    # 0.62 -> 0.50 is a 19% relative drop: past the monitor floor, short of decay.
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE, live=_live(0.50), baseline_win_rate=0.62
    )
    assert result.state is LifecycleState.MONITORING
    assert result.reason is DecayReason.UNDERPERFORMING
    # Still evidence, just watched. Losing the label and losing the standing are
    # different steps.
    assert result.usable_as_support is True


def test_a_clear_shortfall_stops_it_counting_as_support() -> None:
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE, live=_live(0.35), baseline_win_rate=0.62
    )
    assert result.state is LifecycleState.DECAYED
    assert result.usable_as_support is False


def test_a_negative_mean_r_starts_monitoring_even_at_a_healthy_win_rate() -> None:
    """Winning often and losing money is the failure a win rate hides."""
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE,
        live=_live(0.62, mean_r=-0.4),
        baseline_win_rate=0.62,
    )
    assert result.state is LifecycleState.MONITORING


def test_a_collapsed_profit_factor_disables_whatever_the_win_rate_says() -> None:
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE,
        live=_live(0.80, pf=0.9),
        baseline_win_rate=0.62,
    )
    assert result.state is LifecycleState.DISABLED
    assert result.reason is DecayReason.PROFIT_FACTOR_COLLAPSED
    assert result.usable_as_support is False


def test_an_unknown_profit_factor_does_not_pass_the_check_by_default() -> None:
    """None is not "above break-even".

    Defaulting an unmeasured profit factor to something healthy would let a
    losing strategy walk past the one check that catches it.
    """
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE, live=_live(0.60, pf=None), baseline_win_rate=0.62
    )
    assert result.state is LifecycleState.ACTIVE
    # It passed on the win rate, not on an invented profit factor — a genuinely
    # bad one still disables it.
    worse = evaluate_lifecycle(
        current=LifecycleState.ACTIVE, live=_live(0.60, pf=0.5), baseline_win_rate=0.62
    )
    assert worse.state is LifecycleState.DISABLED


def test_a_downgrade_is_immediate_and_an_upgrade_is_earned_twice() -> None:
    """The asymmetry, end to end.

    Down in one evaluation, back up only after `recovery_streak` consecutive
    healthy ones — so a single good result cannot re-promote a broken strategy.
    """
    down = evaluate_lifecycle(
        current=LifecycleState.ACTIVE, live=_live(0.35), baseline_win_rate=0.62
    )
    assert down.state is LifecycleState.DECAYED
    assert down.healthy_streak == 0

    first = evaluate_lifecycle(
        current=LifecycleState.DECAYED,
        live=_live(0.61),
        baseline_win_rate=0.62,
        healthy_streak=down.healthy_streak,
    )
    assert first.state is LifecycleState.DECAYED, "one good window is not a recovery"
    assert first.reason is DecayReason.AWAITING_RECOVERY
    assert first.healthy_streak == 1

    second = evaluate_lifecycle(
        current=LifecycleState.DECAYED,
        live=_live(0.61),
        baseline_win_rate=0.62,
        healthy_streak=first.healthy_streak,
    )
    assert second.state is LifecycleState.ACTIVE
    assert second.reason is DecayReason.RECOVERED
    assert second.healthy_streak == 0


def test_a_relapse_resets_the_recovery_streak() -> None:
    """Progress has to be continuous, or "two healthy evaluations" degrades into
    "two healthy evaluations eventually"."""
    first = evaluate_lifecycle(
        current=LifecycleState.DECAYED,
        live=_live(0.61),
        baseline_win_rate=0.62,
        healthy_streak=0,
    )
    assert first.healthy_streak == 1

    relapse = evaluate_lifecycle(
        current=LifecycleState.DECAYED,
        live=_live(0.40),
        baseline_win_rate=0.62,
        healthy_streak=first.healthy_streak,
    )
    assert relapse.state is LifecycleState.DECAYED
    assert relapse.healthy_streak == 0


def test_disabled_is_terminal() -> None:
    """Auto-reviving a strategy that fell through break-even is how a system
    unlearns."""
    result = evaluate_lifecycle(
        current=LifecycleState.DISABLED,
        live=_live(0.95, pf=5.0),
        baseline_win_rate=0.40,
        healthy_streak=9,
    )
    assert result.state is LifecycleState.DISABLED
    assert result.reason is DecayReason.MANUAL_REVIEW


def test_no_baseline_means_no_measured_shortfall() -> None:
    """A first window has nothing to have decayed from.

    Treating an absent baseline as zero would compute a shortfall of 100% and
    decay every strategy the moment it accumulated enough outcomes to be judged.
    """
    result = evaluate_lifecycle(
        current=LifecycleState.ACTIVE, live=_live(0.20), baseline_win_rate=None
    )
    assert result.state is LifecycleState.ACTIVE
    assert result.win_rate_drop == 0.0

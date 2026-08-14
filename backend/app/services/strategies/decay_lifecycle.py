"""An edge does not stop working all at once.

The lifecycle this replaces was binary — fine, or suspended — which is too blunt
in both directions. It suspends on a run of bad luck, and it keeps a slowly
rotting edge fully live until it crosses one hard line. The real path has four
states:

    active → monitoring → decayed → disabled

**Asymmetric on purpose.** A downgrade takes effect immediately; an upgrade
requires consecutive healthy evaluations. One good result must not re-promote a
broken strategy, and waiting for confirmation before *demoting* one would spend
the confirmation on the reader's account.

**A minimum sample before any downgrade.** Noise is not decay. Below the floor
the state is held where it is and the reason says why, rather than a strategy
being demoted for a bad fortnight.

**`disabled` is terminal.** Nothing auto-revives it. A strategy whose profit
factor fell through break-even is not a strategy having a rough patch, and a
system that quietly promotes it back the moment the numbers wobble upward has
learned nothing.

**What "expected" means here (D7).** There is no backtest to compare against, so
the baseline is this strategy's *own earlier record*: the window before the one
being judged. That is also what fixes the defect this replaces — the previous
implementation captured an all-time average once, on first sight, and compared
against it forever, so a strategy could never decay relative to anything but its
own first impression.

Pure policy. It decides a **label**. It never edits a plan, never executes, and
never loosens a statistical gate: a decayed strategy simply stops counting as
support.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = [
    "LifecycleState",
    "DecayReason",
    "LivePerformance",
    "DecayThresholds",
    "DEFAULT_DECAY_THRESHOLDS",
    "LifecycleEvaluation",
    "evaluate_lifecycle",
]


class LifecycleState(StrEnum):
    ACTIVE = "active"
    MONITORING = "monitoring"
    DECAYED = "decayed"
    DISABLED = "disabled"


class DecayReason(StrEnum):
    """Reason codes; the words are chosen where the reader's language is known."""

    HEALTHY = "DECAY_HEALTHY"
    INSUFFICIENT_SAMPLE = "DECAY_INSUFFICIENT_SAMPLE"
    UNDERPERFORMING = "DECAY_UNDERPERFORMING"
    CLEARLY_WORSE = "DECAY_CLEARLY_WORSE"
    PROFIT_FACTOR_COLLAPSED = "DECAY_PROFIT_FACTOR_COLLAPSED"
    AWAITING_RECOVERY = "DECAY_AWAITING_RECOVERY"
    RECOVERED = "DECAY_RECOVERED"
    MANUAL_REVIEW = "DECAY_MANUAL_REVIEW"


_ORDER: dict[LifecycleState, int] = {
    LifecycleState.ACTIVE: 0,
    LifecycleState.MONITORING: 1,
    LifecycleState.DECAYED: 2,
    LifecycleState.DISABLED: 3,
}


@dataclass(frozen=True, slots=True)
class LivePerformance:
    sample_size: int
    win_rate: float | None
    profit_factor: float | None
    #: Optional. Reported when the outcomes carry R multiples and omitted when
    #: they do not — an absent metric must not be read as a value of zero.
    mean_r: float | None = None


@dataclass(frozen=True, slots=True)
class DecayThresholds:
    #: Below this sample nothing is downgraded. Noise is not decay.
    min_sample_for_judgement: int = 20
    #: Relative win-rate shortfall that starts monitoring (0.15 = 15% worse).
    monitor_win_rate_drop: float = 0.15
    #: Relative shortfall that marks the edge decayed.
    decayed_win_rate_drop: float = 0.30
    #: Profit factor at or below which the edge is gone, whatever the win rate.
    disabled_profit_factor: float = 1.0
    #: Consecutive healthy evaluations required to climb back up.
    recovery_streak: int = 2


DEFAULT_DECAY_THRESHOLDS = DecayThresholds()


@dataclass(frozen=True, slots=True)
class LifecycleEvaluation:
    state: LifecycleState
    reason: DecayReason
    #: May this strategy still count as statistical support? Deliberately not
    #: named for execution — Leovee places no orders (D4). What a decayed
    #: strategy loses is its standing as evidence, not a permission to trade.
    usable_as_support: bool
    healthy_streak: int
    #: The measured shortfall against the baseline, for the reader.
    win_rate_drop: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "reason": self.reason.value,
            "usable_as_support": self.usable_as_support,
            "healthy_streak": self.healthy_streak,
            "win_rate_drop": self.win_rate_drop,
        }


def _settle(
    state: LifecycleState,
    reason: DecayReason,
    healthy_streak: int,
    drop: float | None = None,
) -> LifecycleEvaluation:
    return LifecycleEvaluation(
        state=state,
        reason=reason,
        usable_as_support=state in (LifecycleState.ACTIVE, LifecycleState.MONITORING),
        healthy_streak=healthy_streak,
        win_rate_drop=drop,
    )


def evaluate_lifecycle(
    *,
    current: LifecycleState,
    live: LivePerformance,
    baseline_win_rate: float | None,
    healthy_streak: int = 0,
    thresholds: DecayThresholds = DEFAULT_DECAY_THRESHOLDS,
) -> LifecycleEvaluation:
    """The next state, given the recent window and the one before it."""
    prior_streak = max(0, healthy_streak)

    if current is LifecycleState.DISABLED:
        # Terminal until someone looks at it. Auto-reviving a strategy whose
        # profit factor fell through break-even is how a system unlearns.
        return _settle(LifecycleState.DISABLED, DecayReason.MANUAL_REVIEW, 0)

    if live.sample_size < thresholds.min_sample_for_judgement:
        return _settle(current, DecayReason.INSUFFICIENT_SAMPLE, prior_streak)

    if live.profit_factor is not None and live.profit_factor <= thresholds.disabled_profit_factor:
        # Below break-even the edge is gone whatever the win rate says: a
        # strategy can win often and still lose money, and the win rate is the
        # number that hides it.
        return _settle(LifecycleState.DISABLED, DecayReason.PROFIT_FACTOR_COLLAPSED, 0)

    drop = 0.0
    if baseline_win_rate is not None and baseline_win_rate > 0 and live.win_rate is not None:
        drop = (baseline_win_rate - live.win_rate) / baseline_win_rate

    if drop >= thresholds.decayed_win_rate_drop:
        target, reason = LifecycleState.DECAYED, DecayReason.CLEARLY_WORSE
    elif drop >= thresholds.monitor_win_rate_drop or (live.mean_r is not None and live.mean_r < 0):
        target, reason = LifecycleState.MONITORING, DecayReason.UNDERPERFORMING
    else:
        target, reason = LifecycleState.ACTIVE, DecayReason.HEALTHY

    if _ORDER[target] > _ORDER[current]:
        # Down immediately. Waiting for confirmation before demoting spends the
        # confirmation on the reader.
        return _settle(target, reason, 0, drop)

    if _ORDER[target] == _ORDER[current]:
        # Holding. A healthy reading at a demoted level counts toward recovery;
        # an unhealthy one resets it, so progress has to be continuous.
        healthy = drop < thresholds.monitor_win_rate_drop
        streak = (
            prior_streak
            if target is LifecycleState.ACTIVE
            else (prior_streak + 1 if healthy else 0)
        )
        return _settle(current, reason, streak, drop)

    streak = prior_streak + 1
    if streak < thresholds.recovery_streak:
        return _settle(current, DecayReason.AWAITING_RECOVERY, streak, drop)
    return _settle(target, DecayReason.RECOVERED, 0, drop)

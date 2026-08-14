"""Has this strategy stopped working?

Judged against **its own earlier record**, over a rolling pair of windows: the
last N closed outcomes versus the N before them. Under D7 there is no backtest
to compare against, so the only honest baseline is what this bucket used to do.

That is also the defect this replaces. The previous implementation wrote an
all-time average into `metadata_json["hist_avg_r"]` the first time it saw a
bucket and compared against that number forever — so a strategy could only ever
decay relative to its first impression, and once the running average had absorbed
enough history it could not move far enough to trip anything at all.

The label itself is decided by `strategies/decay_lifecycle`, which is pure. This
module's whole job is reading the two windows correctly and remembering the
state between evaluations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import OutcomeRecord, StrategyStat
from app.services.learning.outcome_recorder import OutcomeKind, TerminalOutcome
from app.services.strategies.decay_lifecycle import (
    LifecycleEvaluation,
    LifecycleState,
    LivePerformance,
    evaluate_lifecycle,
)
from app.services.strategies.thresholds import DECAY_WINDOW

__all__ = ["detect_strategy_decay", "evaluate_strategy_decay"]

_SUCCESS_OUTCOME = "TARGET_REACHED"


async def _windows(
    session: AsyncSession, terminal: TerminalOutcome
) -> tuple[list[OutcomeRecord], list[OutcomeRecord]]:
    """The recent window and the one immediately before it, newest first.

    Only PLAN outcomes: a self-reported trade says what the user did, and a
    strategy does not decay because someone stopped taking it.
    """
    rows = list(
        (
            await session.execute(
                select(OutcomeRecord)
                .where(
                    OutcomeRecord.workspace_id == terminal.workspace_id,
                    OutcomeRecord.kind == OutcomeKind.PLAN.value,
                )
                .order_by(OutcomeRecord.recorded_at.desc(), OutcomeRecord.id.desc())
                .limit(DECAY_WINDOW * 2)
            )
        )
        .scalars()
        .all()
    )
    return rows[:DECAY_WINDOW], rows[DECAY_WINDOW : DECAY_WINDOW * 2]


def _win_rate(rows: list[OutcomeRecord]) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row.outcome == _SUCCESS_OUTCOME) / len(rows)


def _profit_factor(rows: list[OutcomeRecord]) -> float | None:
    """Gross win over gross loss. None when no R multiples were recorded.

    None rather than a default: a strategy with no R data has an *unknown*
    profit factor, and defaulting it to something above break-even would let a
    losing strategy pass the one check that catches "wins often, loses money".
    """
    values = [float(row.r_multiple) for row in rows if row.r_multiple is not None]
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if gains == 0.0 and losses == 0.0:
        return None
    if losses == 0.0:
        # Wins and no losses in the window. Not infinity — a number the caller
        # would then compare against a threshold and always pass.
        return None
    return gains / losses


def _mean_r(rows: list[OutcomeRecord]) -> float | None:
    values = [float(row.r_multiple) for row in rows if row.r_multiple is not None]
    return sum(values) / len(values) if values else None


async def evaluate_strategy_decay(
    session: AsyncSession, terminal: TerminalOutcome
) -> LifecycleEvaluation | None:
    """Judge the bucket this outcome belongs to, and remember the verdict."""
    stat = await session.scalar(
        select(StrategyStat).where(
            StrategyStat.workspace_id == terminal.workspace_id,
            StrategyStat.strategy_code == terminal.strategy_code,
            StrategyStat.setup_type == terminal.setup_type,
            StrategyStat.regime_bucket == terminal.regime_bucket,
            StrategyStat.session_bucket == terminal.session_bucket,
            StrategyStat.volatility_bucket == terminal.volatility_bucket,
        )
    )
    if stat is None:
        return None

    recent, previous = await _windows(session, terminal)
    metadata: dict[str, Any] = dict(stat.metadata_json or {})
    current = LifecycleState(metadata.get("lifecycle_state", LifecycleState.ACTIVE.value))

    evaluation = evaluate_lifecycle(
        current=current,
        live=LivePerformance(
            sample_size=len(recent),
            win_rate=_win_rate(recent),
            profit_factor=_profit_factor(recent),
            mean_r=_mean_r(recent),
        ),
        baseline_win_rate=_win_rate(previous),
        healthy_streak=int(metadata.get("healthy_streak", 0)),
    )

    stat.metadata_json = {
        **metadata,
        "lifecycle_state": evaluation.state.value,
        "healthy_streak": evaluation.healthy_streak,
        "decay_reason": evaluation.reason.value,
        "win_rate_drop": evaluation.win_rate_drop,
    }
    # The flag other code reads. Kept in step with the state rather than being a
    # second, independently-updated opinion about the same thing.
    stat.suspended = not evaluation.usable_as_support
    if stat.avg_r is not None and (mean := _mean_r(recent)) is not None:
        stat.expectancy = Decimal(str(round(mean, 4)))
    return evaluation


async def detect_strategy_decay(session: AsyncSession, terminal: TerminalOutcome) -> bool:
    """Whether this outcome left the bucket unusable as support."""
    evaluation = await evaluate_strategy_decay(session, terminal)
    return evaluation is not None and not evaluation.usable_as_support

"""What happens when something finishes: record it, then let it move the numbers.

**The recording gates everything else.** Every step below is an increment, and
an increment is not idempotent — so if the outcome was already recorded, the
aggregates behind it have already moved and running them again would double
every one. The recorder reports whether it was the writer; a repeat stops here.

**Only a plan outcome calibrates.** Confidence is a claim the analysis made, so
only the analysis being right or wrong can grade it. A self-reported trade says
what the user did, which is behaviour worth learning from (M8's trading DNA) and
worth nothing at all as evidence about the analysis. Feeding both into one win
rate lets a plan taken twice count twice and a plan ignored count once.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.rls import set_rls_session_context
from app.observability.prometheus import recommendation_outcomes_total
from app.services.learning.calibration import update_calibration_bins
from app.services.learning.decay import detect_strategy_decay
from app.services.learning.memory_writer import LessonProposal, propose_lessons_from_outcome
from app.services.learning.outcome_recorder import OutcomeKind, OutcomeRecorder, TerminalOutcome
from app.services.learning.statistics import update_strategy_stats, update_symbol_profile

__all__ = ["run_learning_pipeline"]


async def run_learning_pipeline(
    session: AsyncSession,
    terminal: TerminalOutcome,
    *,
    lesson_proposals: list[LessonProposal] | None = None,
) -> dict[str, Any]:
    """Deterministic learning steps; optional schema-validated lesson proposals."""
    # The GUCs directly, not bind_workspace_rls: the pipeline is reached from
    # workers and hooks that hold an outcome, not a TenantContext, and
    # manufacturing a context here would mean inventing a user_id and a role for
    # a step that has neither.
    await set_rls_session_context(
        session,
        tenant_id=terminal.tenant_id,
        workspace_id=terminal.workspace_id,
    )

    recorded = await OutcomeRecorder.record(session, terminal)
    if recorded.created:
        recommendation_outcomes_total.labels(terminal.outcome, terminal.kind.value).inc()
    if not recorded.created:
        # Already counted. Saying so is the whole point: the caller gets to
        # distinguish "recorded" from "recorded again", and nothing downstream
        # increments a second time.
        return {
            "outcome_record_id": str(recorded.row.id),
            "recorded": False,
            "reason": "already recorded",
            "strategy_decay_detected": False,
            "lessons_created": 0,
        }

    decay = False
    if terminal.kind is OutcomeKind.PLAN:
        await update_strategy_stats(session, terminal)
        await update_calibration_bins(session, terminal)
        decay = await detect_strategy_decay(session, terminal)

    # Both kinds: the symbol profile is a record of what happened around this
    # instrument, and a reported trade is part of that.
    await update_symbol_profile(session, terminal)

    lessons = []
    if lesson_proposals:
        lessons = await propose_lessons_from_outcome(session, terminal, lesson_proposals)
    return {
        "outcome_record_id": str(recorded.row.id),
        "recorded": True,
        "kind": terminal.kind.value,
        "strategy_decay_detected": decay,
        "lessons_created": len(lessons),
    }

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.learning.calibration import update_calibration_bins
from app.services.learning.decay import detect_strategy_decay
from app.services.learning.memory_writer import LessonProposal, propose_lessons_from_outcome
from app.services.learning.outcome_recorder import OutcomeRecorder, TerminalOutcome
from app.services.learning.statistics import update_strategy_stats, update_symbol_profile


async def run_learning_pipeline(
    session: AsyncSession,
    terminal: TerminalOutcome,
    *,
    lesson_proposals: list[LessonProposal] | None = None,
) -> dict[str, object]:
    """Deterministic learning steps; optional schema-validated lesson proposals."""
    outcome_row = await OutcomeRecorder.record(session, terminal)
    await update_strategy_stats(session, terminal)
    await update_symbol_profile(session, terminal)
    await update_calibration_bins(session, terminal)
    decay = await detect_strategy_decay(session, terminal)
    lessons = []
    if lesson_proposals:
        lessons = await propose_lessons_from_outcome(session, terminal, lesson_proposals)
    return {
        "outcome_record_id": str(outcome_row.id),
        "strategy_decay_detected": decay,
        "lessons_created": len(lessons),
    }

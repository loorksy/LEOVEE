"""Recording that something finished, exactly once.

The learning loop's every conclusion is an average over these rows, so a
duplicate is not a cosmetic problem — it is a second vote from one event, and
it moves a win rate in the direction of whatever happened to be recorded twice.

An adversarial audit found three independent ways to cast that second vote, all
reproduced against a real database:

1. `thesis_monitor_service` transitions a thesis *and* its recommendation for
   one market event, and both transitions fire the pipeline;
2. a terminal transition repeated — a retried request, or a user closing a plan
   the tracker already closed — re-fires it, because the state machine returns
   silently when the status already equals the one asked for;
3. a manual transition racing the tracker: both read a non-terminal status,
   both decide, both record.

Only the third is a concurrency bug. The first two are ordinary flows. What all
three share is that no read-then-decide guard in Python can stop them, so the
guarantee lives in a unique key on the table and `record` reports honestly when
it was the one that lost.

**A plan outcome and a trade outcome are different facts.** The analysis being
right is what calibrates confidence. What the user did about it is behaviour
(D4 — Leovee places no orders, so a trade is a journal entry). Counting them
together lets a plan the user took twice move the statistics twice, and a plan
they ignored count once instead of not at all.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.models.learning import OutcomeRecord

__all__ = [
    "OutcomeKind",
    "TerminalOutcome",
    "RecordResult",
    "OutcomeRecorder",
    "RECORDER_VERSION",
]

RECORDER_VERSION = "2"


class OutcomeKind(StrEnum):
    #: The analysis was right or wrong. The only kind that calibrates confidence.
    PLAN = "PLAN"
    #: What the user reported doing. Behaviour, not accuracy.
    TRADE = "TRADE"


@dataclass(frozen=True, slots=True)
class TerminalOutcome:
    workspace_id: uuid.UUID
    tenant_id: uuid.UUID
    thesis_id: uuid.UUID | None
    recommendation_id: uuid.UUID | None
    trade_id: uuid.UUID | None
    outcome: str
    r_multiple: Decimal | None
    source: str
    facts: dict[str, Any]
    strategy_code: str
    setup_type: str
    regime_bucket: str
    session_bucket: str
    volatility_bucket: str
    symbol_id: uuid.UUID | None
    confidence_stated: Decimal | None
    success: bool
    kind: OutcomeKind = OutcomeKind.PLAN

    @property
    def dedupe_key(self) -> str:
        """One key per real-world event.

        A recommendation-linked outcome keys on the **recommendation alone**,
        not on the status it reached. A plan closes once, however many
        components notice — and the thesis monitor notices twice on purpose,
        once for the thesis and once for the plan behind it. Including the
        status would give those two notices different keys and let the same
        close be counted twice, which is the defect this key exists to close.
        """
        if self.kind is OutcomeKind.TRADE and self.trade_id is not None:
            return f"trade:{self.trade_id}"
        if self.recommendation_id is not None:
            return f"rec:{self.recommendation_id}"
        if self.thesis_id is not None:
            return f"thesis:{self.thesis_id}"
        if self.trade_id is not None:
            return f"trade:{self.trade_id}"
        # No anchor at all. A key from nothing would collide with every other
        # anchorless outcome in the workspace and silently drop all but one.
        return f"orphan:{uuid.uuid4()}"

    def with_buckets(
        self,
        *,
        strategy_code: str,
        setup_type: str,
        regime_bucket: str,
        session_bucket: str,
        volatility_bucket: str,
    ) -> TerminalOutcome:
        return replace(
            self,
            strategy_code=strategy_code,
            setup_type=setup_type,
            regime_bucket=regime_bucket,
            session_bucket=session_bucket,
            volatility_bucket=volatility_bucket,
        )


@dataclass(frozen=True, slots=True)
class RecordResult:
    row: OutcomeRecord
    #: False when this event was already recorded. The caller must skip the rest
    #: of the pipeline: the row it is looking at is somebody else's write, and
    #: the aggregates behind it have already been moved.
    created: bool


class OutcomeRecorder:
    """Records terminal outcomes deterministically — no model call."""

    @staticmethod
    async def record(session: AsyncSession, terminal: TerminalOutcome) -> RecordResult:
        key = terminal.dedupe_key
        statement = (
            pg_insert(OutcomeRecord)
            .values(
                id=uuid.uuid4(),
                tenant_id=terminal.tenant_id,
                workspace_id=terminal.workspace_id,
                thesis_id=terminal.thesis_id,
                recommendation_id=terminal.recommendation_id,
                trade_id=terminal.trade_id,
                outcome=terminal.outcome,
                kind=terminal.kind.value,
                dedupe_key=key,
                r_multiple=terminal.r_multiple,
                source=terminal.source,
                facts_json=terminal.facts,
                recorded_at=utc_now(),
                recorder_version=RECORDER_VERSION,
            )
            .on_conflict_do_nothing(constraint="uq_outcome_record_dedupe")
            .returning(OutcomeRecord.id)
        )
        written = await session.scalar(statement)
        await session.flush()
        if written is not None:
            row = await session.get(OutcomeRecord, written)
            assert row is not None
            return RecordResult(row=row, created=True)

        # Lost the race, or this is a repeat. Return the row that won so the
        # caller can reference it — but say plainly that it did not write it.
        existing = await session.scalar(
            select(OutcomeRecord).where(
                OutcomeRecord.workspace_id == terminal.workspace_id,
                OutcomeRecord.dedupe_key == key,
            )
        )
        if existing is None:
            # The conflict was real but the row is invisible: RLS is bound to a
            # different workspace than the one being written. Failing loudly is
            # right — silently returning "already recorded" would drop the
            # outcome and report success.
            raise RuntimeError(
                f"outcome {key} conflicted but is not readable in this workspace; "
                "check the bound RLS context"
            )
        return RecordResult(row=existing, created=False)

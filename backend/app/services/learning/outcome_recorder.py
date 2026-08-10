from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.models.learning import OutcomeRecord


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


RECORDER_VERSION = "1"


class OutcomeRecorder:
    """Records terminal outcomes deterministically — no LLM."""

    @staticmethod
    async def record(session: AsyncSession, terminal: TerminalOutcome) -> OutcomeRecord:
        row = OutcomeRecord(
            tenant_id=terminal.tenant_id,
            workspace_id=terminal.workspace_id,
            thesis_id=terminal.thesis_id,
            recommendation_id=terminal.recommendation_id,
            trade_id=terminal.trade_id,
            outcome=terminal.outcome,
            r_multiple=terminal.r_multiple,
            source=terminal.source,
            facts_json=terminal.facts,
            recorded_at=utc_now(),
            recorder_version=RECORDER_VERSION,
        )
        session.add(row)
        await session.flush()
        return row

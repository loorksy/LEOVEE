from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RecommendationStatus, ThesisStatus
from app.models.recommendation import Recommendation, Thesis
from app.services.learning.outcome_recorder import (
    OutcomeKind,
    TerminalOutcome,
)
from app.services.learning.pipeline import run_learning_pipeline

# Re-exported, not redefined. This module used to carry its own copy of the same
# frozenset, which is two places to change and one of them will be forgotten —
# and the two are compared against each other every time a plan closes.
from app.services.recommendation_lifecycle import (  # noqa: E402  (grouped with its siblings)
    TERMINAL_RECOMMENDATION_STATUSES,
)
from app.services.strategies.matching_keys import classification_from_evidence

TERMINAL_THESIS_STATUSES = frozenset(
    {
        ThesisStatus.TARGET_REACHED,
        ThesisStatus.INVALIDATED,
        ThesisStatus.EXPIRED,
    }
)


def _success_for_outcome(outcome: str) -> bool:
    return outcome == RecommendationStatus.TARGET_REACHED.value


def _terminal_from_recommendation(
    rec: Recommendation,
    *,
    outcome: str,
    facts: dict[str, Any] | None = None,
) -> TerminalOutcome:
    # One reader, one writer, one shape. This used to be five separate lookups
    # of five top-level keys with five separate defaults — and nothing wrote any
    # of them, so every outcome in the product's history filed under the
    # constant DEFAULT/ANY/ANY/ANY/ANY and the five bucket columns aggregated
    # everything into a single undifferentiated pile.
    buckets = classification_from_evidence(rec.evidence_json)
    stated = rec.confidence_calibrated
    return TerminalOutcome(
        workspace_id=rec.workspace_id,
        tenant_id=rec.tenant_id,
        thesis_id=None,
        recommendation_id=rec.id,
        trade_id=None,
        outcome=outcome,
        r_multiple=None,
        source="LIVE",
        facts=facts or {"recommendation_id": str(rec.id)},
        strategy_code=buckets.strategy_code,
        setup_type=buckets.setup_type,
        regime_bucket=buckets.regime_bucket,
        session_bucket=buckets.session_bucket,
        volatility_bucket=buckets.volatility_bucket,
        symbol_id=rec.symbol_id,
        confidence_stated=stated,
        success=_success_for_outcome(outcome),
    )


async def on_recommendation_terminal_status(
    session: AsyncSession,
    rec: Recommendation,
    *,
    new_status: RecommendationStatus,
    facts: dict[str, Any] | None = None,
) -> dict[str, object] | None:
    """One plan closing, once.

    The thesis monitor calls this *and* `on_thesis_terminal_status` for a single
    market event, on purpose — a thesis and the plan behind it are both real
    things that ended. Both produce the same dedupe key, so the second call is
    recorded as a repeat and moves nothing. That is deliberate: the ownership
    question ("which of the two should drive learning") has no stable answer at
    the call site, and the key answers it at the table instead.
    """
    if new_status not in TERMINAL_RECOMMENDATION_STATUSES:
        return None
    terminal = _terminal_from_recommendation(rec, outcome=new_status.value, facts=facts)
    return await run_learning_pipeline(session, terminal)


async def on_thesis_terminal_status(
    session: AsyncSession,
    thesis: Thesis,
    rec: Recommendation,
    *,
    new_status: ThesisStatus,
    r_multiple: Decimal | None = None,
    facts: dict[str, Any] | None = None,
) -> dict[str, object] | None:
    if new_status not in TERMINAL_THESIS_STATUSES:
        return None
    terminal = _terminal_from_recommendation(
        rec,
        outcome=new_status.value,
        facts={
            **(facts or {}),
            "thesis_id": str(thesis.id),
        },
    )
    terminal = TerminalOutcome(
        workspace_id=terminal.workspace_id,
        tenant_id=terminal.tenant_id,
        thesis_id=thesis.id,
        recommendation_id=rec.id,
        trade_id=terminal.trade_id,
        outcome=new_status.value,
        r_multiple=r_multiple,
        source=terminal.source,
        facts=terminal.facts,
        strategy_code=terminal.strategy_code,
        setup_type=terminal.setup_type,
        regime_bucket=terminal.regime_bucket,
        session_bucket=terminal.session_bucket,
        volatility_bucket=terminal.volatility_bucket,
        symbol_id=terminal.symbol_id,
        confidence_stated=terminal.confidence_stated,
        success=_success_for_outcome(new_status.value),
    )
    return await run_learning_pipeline(session, terminal)


async def on_trade_closed(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    recommendation_id: uuid.UUID | None,
    thesis_id: uuid.UUID | None,
    trade_id: uuid.UUID,
    symbol_id: uuid.UUID,
    outcome: str,
    r_multiple: Decimal | None,
    facts: dict[str, Any],
) -> dict[str, object]:
    terminal = TerminalOutcome(
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        thesis_id=thesis_id,
        recommendation_id=recommendation_id,
        trade_id=trade_id,
        outcome=outcome,
        r_multiple=r_multiple,
        source="LIVE",
        facts=facts,
        strategy_code=facts.get("strategy_code", "DEFAULT"),
        setup_type=facts.get("setup_type", "ANY"),
        regime_bucket=facts.get("regime_bucket", "ANY"),
        session_bucket=facts.get("session_bucket", "ANY"),
        volatility_bucket=facts.get("volatility_bucket", "ANY"),
        symbol_id=symbol_id,
        confidence_stated=None,
        success=outcome == RecommendationStatus.TARGET_REACHED.value,
        # A trade is what the *user* did, self-reported (D4 — Leovee places no
        # orders). It is behaviour, and behaviour cannot grade a confidence the
        # analysis stated: a plan the user took twice would move the win rate
        # twice, and one they ignored would not move it at all.
        kind=OutcomeKind.TRADE,
    )
    return await run_learning_pipeline(session, terminal)

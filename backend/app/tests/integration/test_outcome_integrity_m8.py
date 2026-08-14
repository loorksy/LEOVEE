"""One closed plan, one recorded outcome — and one bucket it can be found in.

Every conclusion the learning loop reaches is an average over `outcome_records`,
which makes a duplicated row a second vote from a single event. An adversarial
audit found three independent ways to cast that vote and reproduced all three;
each has a test here.

The fourth test is the other half of the same problem: the five columns those
averages are grouped by were never written, so every outcome in the product's
history filed under one constant bucket. A perfectly deduplicated average over
one undifferentiated pile is still not a measurement of anything.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationDirection, RecommendationStatus, ThesisStatus
from app.models.learning import CalibrationBin, OutcomeRecord, StrategyStat
from app.models.recommendation import Recommendation
from app.services import market_data, recommendation_service
from app.services.learning.outcome_recorder import OutcomeKind, TerminalOutcome
from app.services.learning.pipeline import run_learning_pipeline
from app.services.learning.terminal_hooks import on_recommendation_terminal_status
from app.services.strategies.matching_keys import UNKNOWN, classification_from_evidence
from app.tests.conftest import seed_user_org


async def _tenant(session: AsyncSession, *, email: str, slug: str) -> TenantContext:
    user, _org, _member = await seed_user_org(session, email=email, slug=slug)
    ctx = await resolve_tenant_context(session, user.id)
    await bind_workspace_rls(session, ctx)
    return ctx


async def _plan(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    status: RecommendationStatus = RecommendationStatus.READY,
    evidence: dict[str, Any] | None = None,
) -> Recommendation:
    symbol = await market_data.get_or_create_symbol(session, "XAUUSD")
    rec = Recommendation(
        id=uuid.uuid4(),
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol_id=symbol.id,
        direction=RecommendationDirection.BUY,
        status=status,
        entry=Decimal("2000"),
        stop=Decimal("1996"),
        targets_json=[2008.0],
        confidence_calibrated=Decimal("0.62"),
        timeframe="M15",
        evidence_json=evidence or {},
    )
    session.add(rec)
    await session.flush()
    return rec


async def _counts(session: AsyncSession, tenant: TenantContext) -> tuple[int, int, int]:
    await bind_workspace_rls(session, tenant)
    outcomes = await session.scalar(select(func.count()).select_from(OutcomeRecord)) or 0
    occurrences = await session.scalar(select(func.coalesce(func.sum(StrategyStat.occurrences), 0)))
    predictions = await session.scalar(
        select(func.coalesce(func.sum(CalibrationBin.predicted_count), 0))
    )
    return int(outcomes), int(occurrences or 0), int(predictions or 0)


@pytest.mark.asyncio
async def test_the_thesis_and_the_plan_closing_together_is_one_outcome(
    db_session: AsyncSession,
) -> None:
    """The thesis monitor transitions both, on purpose, for one market event.

    Both hooks are correct to fire — a thesis and the plan behind it are both
    real things that ended. What must not happen is the market event being
    counted twice, and the dedupe key is what stops it: both produce `rec:<id>`.
    """
    tenant = await _tenant(db_session, email="oi1@example.com", slug="oi1")
    rec = await _plan(db_session, tenant)

    first = await on_recommendation_terminal_status(
        db_session, rec, new_status=RecommendationStatus.TARGET_REACHED
    )
    thesis_shaped = TerminalOutcome(
        workspace_id=rec.workspace_id,
        tenant_id=rec.tenant_id,
        thesis_id=uuid.uuid4(),
        recommendation_id=rec.id,
        trade_id=None,
        outcome=ThesisStatus.TARGET_REACHED.value,
        r_multiple=Decimal("2.0"),
        source="LIVE",
        facts={},
        strategy_code="x",
        setup_type="y",
        regime_bucket="TRENDING",
        session_bucket="LONDON",
        volatility_bucket="NORMAL",
        symbol_id=rec.symbol_id,
        confidence_stated=Decimal("0.62"),
        success=True,
    )
    second = await run_learning_pipeline(db_session, thesis_shaped)

    assert first is not None and first["recorded"] is True
    assert second["recorded"] is False
    assert await _counts(db_session, tenant) == (1, 1, 1)


@pytest.mark.asyncio
async def test_closing_a_plan_that_is_already_closed_changes_nothing(
    db_session: AsyncSession,
) -> None:
    """A retried request, or a user closing what the tracker already closed.

    The state machine returns silently when the status already equals the one
    asked for, so nothing upstream raised — the third call used to record a
    third loss for one plan.
    """
    tenant = await _tenant(db_session, email="oi2@example.com", slug="oi2")
    rec = await _plan(db_session, tenant)

    for _ in range(3):
        await recommendation_service.transition_recommendation_status(
            db_session, tenant, rec.id, new_status=RecommendationStatus.INVALIDATED
        )

    assert await _counts(db_session, tenant) == (1, 1, 1)
    await db_session.refresh(rec)
    assert rec.status is RecommendationStatus.INVALIDATED


@pytest.mark.asyncio
async def test_a_terminal_plan_cannot_be_moved_to_a_different_ending(
    db_session: AsyncSession,
) -> None:
    """The race the row lock exists for, in its observable form.

    A manual transition and the tracker both read a non-terminal status and both
    decide. Under the lock the loser re-reads and finds the plan already
    finished — so the plan keeps the ending it actually had, and one event
    yields one outcome instead of a win and a loss from the same close.
    """
    tenant = await _tenant(db_session, email="oi3@example.com", slug="oi3")
    rec = await _plan(db_session, tenant)

    await recommendation_service.transition_recommendation_status(
        db_session, tenant, rec.id, new_status=RecommendationStatus.TARGET_REACHED
    )
    await recommendation_service.transition_recommendation_status(
        db_session, tenant, rec.id, new_status=RecommendationStatus.INVALIDATED
    )

    await db_session.refresh(rec)
    assert rec.status is RecommendationStatus.TARGET_REACHED
    outcomes, occurrences, predictions = await _counts(db_session, tenant)
    assert (outcomes, occurrences, predictions) == (1, 1, 1)


@pytest.mark.asyncio
async def test_a_reported_trade_does_not_grade_the_analysis(db_session: AsyncSession) -> None:
    """Behaviour and accuracy are different measurements (D4).

    Leovee places no orders, so a trade is a journal entry: what the user did
    about a plan. Counting it into the same win rate lets a plan taken twice
    move the statistics twice, and a plan ignored not move them at all.
    """
    tenant = await _tenant(db_session, email="oi4@example.com", slug="oi4")
    rec = await _plan(db_session, tenant)

    result = await run_learning_pipeline(
        db_session,
        TerminalOutcome(
            workspace_id=rec.workspace_id,
            tenant_id=rec.tenant_id,
            thesis_id=None,
            recommendation_id=rec.id,
            trade_id=uuid.uuid4(),
            outcome=RecommendationStatus.TARGET_REACHED.value,
            r_multiple=Decimal("1.4"),
            source="LIVE",
            facts={},
            strategy_code="x",
            setup_type="y",
            regime_bucket="TRENDING",
            session_bucket="LONDON",
            volatility_bucket="NORMAL",
            symbol_id=rec.symbol_id,
            confidence_stated=Decimal("0.62"),
            success=True,
            kind=OutcomeKind.TRADE,
        ),
    )

    assert result["recorded"] is True
    outcomes, occurrences, predictions = await _counts(db_session, tenant)
    assert outcomes == 1
    # Recorded as behaviour, and absent from both accuracy measures.
    assert (occurrences, predictions) == (0, 0)


@pytest.mark.asyncio
async def test_outcomes_land_in_the_bucket_the_analysis_was_classified_into(
    db_session: AsyncSession,
) -> None:
    """The other half: five grouping columns that nothing used to write.

    Every outcome in the product's history filed under DEFAULT/ANY/ANY/ANY/ANY —
    one bucket per workspace, holding everything. A win rate over that is a
    statement about the workspace, not about a strategy.
    """
    tenant = await _tenant(db_session, email="oi5@example.com", slug="oi5")
    rec = await _plan(
        db_session,
        tenant,
        evidence={
            "classification": {
                "strategy_code": "double_bottom_trending_m15",
                "setup_type": "DOUBLE_BOTTOM",
                "regime_bucket": "TRENDING",
                "session_bucket": "LONDON",
                "volatility_bucket": "HIGH",
            }
        },
    )

    await on_recommendation_terminal_status(
        db_session, rec, new_status=RecommendationStatus.TARGET_REACHED
    )
    await bind_workspace_rls(db_session, tenant)
    stat = await db_session.scalar(select(StrategyStat))
    assert stat is not None
    assert stat.strategy_code == "double_bottom_trending_m15"
    assert stat.setup_type == "DOUBLE_BOTTOM"
    assert stat.regime_bucket == "TRENDING"
    assert stat.session_bucket == "LONDON"
    assert stat.volatility_bucket == "HIGH"


@pytest.mark.asyncio
async def test_an_unclassified_plan_says_unknown_rather_than_claiming_a_bucket(
    db_session: AsyncSession,
) -> None:
    """UNKNOWN is a fact about the data; ANY is a deliberate wildcard.

    Spelling them the same is how a missing measurement reads as a considered
    decision to aggregate over the dimension.
    """
    tenant = await _tenant(db_session, email="oi6@example.com", slug="oi6")
    rec = await _plan(db_session, tenant, evidence={"engines": {}})

    buckets = classification_from_evidence(rec.evidence_json)
    assert buckets.setup_type == UNKNOWN
    assert buckets.regime_bucket == UNKNOWN
    assert buckets.derived is False


@pytest.mark.asyncio
async def test_decay_reads_the_bucket_the_outcome_moved(db_session: AsyncSession) -> None:
    """It used to read an arbitrary sibling of the same strategy.

    The filter named three of the six key columns, so `scalar()` returned
    whichever row the plan visited first: a London outcome could suspend the
    Asian bucket and leave its own untouched.
    """
    from app.services.learning.decay import detect_strategy_decay

    tenant = await _tenant(db_session, email="oi7@example.com", slug="oi7")
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    common = {
        "tenant_id": tenant.tenant_id,
        "workspace_id": tenant.workspace_id,
        "symbol_id": symbol.id,
        "strategy_code": "orb_trending_m15",
        "setup_type": "BREAKOUT",
    }
    asia = StrategyStat(
        **common,
        regime_bucket="RANGING",
        session_bucket="ASIA",
        volatility_bucket="LOW",
        occurrences=40,
        avg_r=Decimal("-0.9"),
        metadata_json={"hist_avg_r": "1.0"},
    )
    london = StrategyStat(
        **common,
        regime_bucket="TRENDING",
        session_bucket="LONDON",
        volatility_bucket="HIGH",
        occurrences=40,
        avg_r=Decimal("1.8"),
        metadata_json={"hist_avg_r": "1.75"},
    )
    db_session.add_all([asia, london])
    await db_session.flush()

    terminal = TerminalOutcome(
        workspace_id=tenant.workspace_id,
        tenant_id=tenant.tenant_id,
        thesis_id=None,
        recommendation_id=None,
        trade_id=None,
        outcome="TARGET_REACHED",
        r_multiple=None,
        source="LIVE",
        facts={},
        strategy_code="orb_trending_m15",
        setup_type="BREAKOUT",
        regime_bucket="TRENDING",
        session_bucket="LONDON",
        volatility_bucket="HIGH",
        symbol_id=symbol.id,
        confidence_stated=None,
        success=True,
    )
    decayed = await detect_strategy_decay(db_session, terminal)

    # London is healthy against its own baseline, so nothing is suspended —
    # and crucially the unrelated Asian bucket is left alone.
    assert decayed is False
    assert london.suspended is False
    assert asia.suspended is False


@pytest.mark.asyncio
async def test_the_session_bucket_is_read_off_the_clock_not_a_cost_table(
    db_session: AsyncSession,
) -> None:
    """Sessions are participation, not spread (ADR 0010)."""
    from app.services.strategies.matching_keys import SessionBucket, session_bucket_at

    def at(hour: int) -> str:
        return session_bucket_at(datetime(2026, 6, 10, hour, tzinfo=UTC))

    assert at(3) == SessionBucket.ASIA
    assert at(8) == SessionBucket.LONDON
    assert at(14) == SessionBucket.OVERLAP
    assert at(18) == SessionBucket.NEW_YORK
    assert at(23) == SessionBucket.ASIA

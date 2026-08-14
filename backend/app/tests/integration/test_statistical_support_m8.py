"""What the record is allowed to claim, and what it must admit.

Under D7 there is no simulated history, so a brand-new workspace has none at
all. The tests that matter most here are the ones about *absence*: a platform
whose first hundred recommendations quietly carry the authority of statistics it
does not have is worse than one with no statistics layer at all, because the
authority is invisible and the reader has no way to discount it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.learning import StrategyStat
from app.services import market_data
from app.services.strategies import (
    Classification,
    SupportLevel,
    SupportReason,
    assess_support,
)
from app.services.strategies.thresholds import MIN_OUTCOMES_FOR_SUPPORT
from app.tests.conftest import seed_user_org

PLAN = Classification(
    strategy_code="double_bottom_trending_m15",
    setup_type="DOUBLE_BOTTOM",
    regime_bucket="TRENDING",
    session_bucket="LONDON",
    volatility_bucket="HIGH",
)


async def _tenant(session: AsyncSession, *, email: str, slug: str) -> TenantContext:
    user, _org, _member = await seed_user_org(session, email=email, slug=slug)
    ctx = await resolve_tenant_context(session, user.id)
    await bind_workspace_rls(session, ctx)
    return ctx


async def _record(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    occurrences: int,
    wins: int,
    setup: str = PLAN.setup_type,
    regime: str = PLAN.regime_bucket,
    session_bucket: str = PLAN.session_bucket,
    volatility: str = PLAN.volatility_bucket,
    suspended: bool = False,
) -> StrategyStat:
    symbol = await market_data.get_or_create_symbol(session, "XAUUSD")
    stat = StrategyStat(
        id=uuid.uuid4(),
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol_id=symbol.id,
        strategy_code=PLAN.strategy_code,
        setup_type=setup,
        regime_bucket=regime,
        session_bucket=session_bucket,
        volatility_bucket=volatility,
        occurrences=occurrences,
        wins=wins,
        avg_r=Decimal("0"),
        suspended=suspended,
    )
    session.add(stat)
    await session.flush()
    return stat


@pytest.mark.asyncio
async def test_a_new_workspace_is_told_it_has_no_record(db_session: AsyncSession) -> None:
    """The cold start, stated rather than implied.

    This is the state every workspace begins in and stays in for a while, so it
    is the most-rendered answer this module gives.
    """
    tenant = await _tenant(db_session, email="ss1@example.com", slug="ss1")
    support = await assess_support(db_session, tenant, PLAN)

    assert support.level is SupportLevel.NONE
    assert support.reason is SupportReason.NO_HISTORY
    assert support.has_support is False
    assert support.outcomes == 0
    assert support.calibration is None


@pytest.mark.asyncio
async def test_a_thin_record_is_provisional_and_still_reports_its_count(
    db_session: AsyncSession,
) -> None:
    """ "Three outcomes, all wins" and "no outcomes" are different things to say."""
    tenant = await _tenant(db_session, email="ss2@example.com", slug="ss2")
    await _record(db_session, tenant, occurrences=3, wins=3)

    support = await assess_support(db_session, tenant, PLAN)
    assert support.level is SupportLevel.PROVISIONAL
    assert support.reason is SupportReason.PROVISIONAL
    assert support.has_support is False
    assert (support.outcomes, support.wins) == (3, 3)
    # Three wins from three is not a 100% strategy, and the interval says so.
    assert support.calibration is not None
    assert support.calibration.statistically_sufficient is False
    assert support.calibration.confidence_low < 0.6


@pytest.mark.asyncio
async def test_the_boundary_between_provisional_and_graded_is_the_stated_one(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="ss3@example.com", slug="ss3")
    await _record(db_session, tenant, occurrences=MIN_OUTCOMES_FOR_SUPPORT - 1, wins=10)
    below = await assess_support(db_session, tenant, PLAN)
    assert below.level is SupportLevel.PROVISIONAL

    await bind_workspace_rls(db_session, tenant)
    row = await db_session.scalar(select(StrategyStat))
    assert row is not None
    row.occurrences = MIN_OUTCOMES_FOR_SUPPORT
    await db_session.flush()

    at_boundary = await assess_support(db_session, tenant, PLAN)
    assert at_boundary.level is not SupportLevel.PROVISIONAL


@pytest.mark.asyncio
async def test_a_large_record_is_graded_on_its_interval_not_its_midpoint(
    db_session: AsyncSession,
) -> None:
    """A wide band on a high win rate is weak evidence however good it looks."""
    tenant = await _tenant(db_session, email="ss4@example.com", slug="ss4")
    await _record(db_session, tenant, occurrences=400, wins=240)

    support = await assess_support(db_session, tenant, PLAN)
    assert support.level is SupportLevel.STRONG
    assert support.reason is SupportReason.PRESENT
    assert support.has_support is True
    assert support.calibration is not None
    assert support.calibration.statistically_sufficient is True
    assert support.calibration.width <= 0.20


@pytest.mark.asyncio
async def test_a_suspended_bucket_is_evidence_against_relying_on_it(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="ss5@example.com", slug="ss5")
    await _record(db_session, tenant, occurrences=200, wins=120, suspended=True)

    support = await assess_support(db_session, tenant, PLAN)
    assert support.level is SupportLevel.WEAK
    assert support.reason is SupportReason.SUSPENDED
    assert support.suspended is True


@pytest.mark.asyncio
async def test_a_wider_bucket_answers_and_says_which_dimensions_it_averaged(
    db_session: AsyncSession,
) -> None:
    """Reporting "no support" while fifty outcomes sit one session over is a
    failure to look — but borrowing them silently is a failure to say so."""
    tenant = await _tenant(db_session, email="ss6@example.com", slug="ss6")
    await _record(db_session, tenant, occurrences=50, wins=30, session_bucket="ASIA")

    support = await assess_support(db_session, tenant, PLAN)
    assert support.outcomes == 50
    assert support.reason is SupportReason.AGGREGATED
    assert "session_bucket" in support.aggregated_over
    assert "volatility_bucket" in support.aggregated_over
    assert "setup_type" not in support.aggregated_over


@pytest.mark.asyncio
async def test_the_exact_bucket_wins_even_when_a_wider_one_has_more(
    db_session: AsyncSession,
) -> None:
    """Trading a small exact sample for a large loose one is the reader's call.

    Preferring the first *sufficient* rung would make it silently, and the
    output would look identical either way.
    """
    tenant = await _tenant(db_session, email="ss7@example.com", slug="ss7")
    await _record(db_session, tenant, occurrences=6, wins=4)
    await _record(db_session, tenant, occurrences=300, wins=180, session_bucket="ASIA")

    support = await assess_support(db_session, tenant, PLAN)
    assert support.outcomes == 6
    assert support.aggregated_over == ()
    assert support.level is SupportLevel.PROVISIONAL


@pytest.mark.asyncio
async def test_one_workspace_record_is_never_evidence_about_another(
    db_session: AsyncSession,
) -> None:
    """The reference implementation had an owner-less fallback for exactly this
    case, labelled "platform evidence". Under RLS it is not expressible."""
    a = await _tenant(db_session, email="ss8a@example.com", slug="ss8a")
    await _record(db_session, a, occurrences=500, wins=320)

    b = await _tenant(db_session, email="ss8b@example.com", slug="ss8b")
    support = await assess_support(db_session, b, PLAN)
    assert support.level is SupportLevel.NONE
    assert support.outcomes == 0

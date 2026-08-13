"""The recommendation lifecycle: transitions, history, and the tracker."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.engines.bar import OHLCBar
from app.models.enums import RecommendationDirection, RecommendationStatus
from app.models.recommendation import Recommendation, RecommendationRevision
from app.services import market_data
from app.services.recommendations import repository, revisions, tracker
from app.services.recommendations.activation import ActivationKind
from app.tests.bars import bar
from app.tests.conftest import seed_user_org


async def _tenant(session: AsyncSession, *, email: str, slug: str) -> TenantContext:
    user, _org, _member = await seed_user_org(session, email=email, slug=slug)
    ctx = await resolve_tenant_context(session, user.id)
    await bind_workspace_rls(session, ctx)
    return ctx


async def _recommendation(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    status: RecommendationStatus = RecommendationStatus.READY,
    direction: RecommendationDirection = RecommendationDirection.BUY,
    entry: str = "2000",
    stop: str = "1996",
    targets: list[float] | None = None,
    **extra: Any,
) -> Recommendation:
    symbol = await market_data.get_or_create_symbol(session, "XAUUSD")
    rec = Recommendation(
        id=uuid.uuid4(),
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol_id=symbol.id,
        direction=direction,
        status=status,
        entry=Decimal(entry),
        stop=Decimal(stop),
        targets_json=targets if targets is not None else [2008.0],
        **extra,
    )
    session.add(rec)
    await session.flush()
    return rec


def _bars(*specs: tuple[float, float, float, float]) -> list[OHLCBar]:
    return [bar(open=o, high=h, low=lo, close=c) for o, h, lo, c in specs]


# --- the tracker -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_stop_traded_through_invalidates(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="t1@example.com", slug="t1")
    rec = await _recommendation(db_session, tenant)

    outcome = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2002, 1995, 1997))
    )
    assert outcome.changed
    assert outcome.status is RecommendationStatus.INVALIDATED
    assert "1996" in (outcome.detail or "")


@pytest.mark.asyncio
async def test_a_stop_hit_beats_a_target_hit_later(db_session: AsyncSession) -> None:
    """A plan whose stop broke is finished whatever happened next.

    Without the ordering, a stop-out that bounced to target is recorded as a
    win — the single most flattering way for a tracker to be wrong.
    """
    tenant = await _tenant(db_session, email="t2@example.com", slug="t2")
    rec = await _recommendation(db_session, tenant)

    outcome = await tracker.evaluate_recommendation(
        db_session,
        tenant,
        rec,
        bars=_bars((2000, 2002, 1995, 1997), (1997, 2010, 1996, 2009)),
    )
    assert outcome.status is RecommendationStatus.INVALIDATED


@pytest.mark.asyncio
async def test_a_stop_is_checked_intrabar_not_on_closes(db_session: AsyncSession) -> None:
    """A stop is an order resting in the book: price trading through it fills it
    whether or not the candle closes there."""
    tenant = await _tenant(db_session, email="t3@example.com", slug="t3")
    rec = await _recommendation(db_session, tenant)

    wicked = _bars((2000, 2002, 1995.5, 2001))
    outcome = await tracker.evaluate_recommendation(db_session, tenant, rec, bars=wicked)
    assert outcome.status is RecommendationStatus.INVALIDATED


@pytest.mark.asyncio
async def test_a_target_reached_closes_the_plan(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="t4@example.com", slug="t4")
    rec = await _recommendation(db_session, tenant)

    outcome = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2009, 1999, 2008))
    )
    assert outcome.status is RecommendationStatus.TARGET_REACHED


@pytest.mark.asyncio
async def test_a_condition_that_fires_makes_the_plan_ready(db_session: AsyncSession) -> None:
    """READY, not ACTIVE: the condition firing means the plan is valid to take,
    not that anyone took it. Leovee never executes."""
    tenant = await _tenant(db_session, email="t5@example.com", slug="t5")
    rec = await _recommendation(
        db_session,
        tenant,
        status=RecommendationStatus.WAITING_CONFIRMATION,
        stop="1990",
        targets=[2050.0],
        activation_rule_json={
            "kind": ActivationKind.CANDLE_CLOSE_ABOVE.value,
            "level": 2005.0,
        },
    )

    still_waiting = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2004, 1999, 2002))
    )
    assert still_waiting.changed is False

    fired = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2010, 1999, 2007))
    )
    assert fired.status is RecommendationStatus.READY
    assert rec.activated_at is None  # READY is not ACTIVE


@pytest.mark.asyncio
async def test_an_unreadable_rule_leaves_the_plan_pending(db_session: AsyncSession) -> None:
    """One bad row must not stop the loop for every other plan."""
    tenant = await _tenant(db_session, email="t6@example.com", slug="t6")
    rec = await _recommendation(
        db_session,
        tenant,
        status=RecommendationStatus.WAITING_CONFIRMATION,
        stop="1990",
        targets=[2050.0],
        activation_rule_json={"kind": "from_a_future_release", "level": 1.0},
    )
    outcome = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2010, 1999, 2007))
    )
    assert outcome.changed is False
    assert outcome.status is RecommendationStatus.WAITING_CONFIRMATION


@pytest.mark.asyncio
async def test_an_expired_plan_is_closed_last(db_session: AsyncSession) -> None:
    """Expiry is what is left when nothing else happened."""
    tenant = await _tenant(db_session, email="t7@example.com", slug="t7")
    rec = await _recommendation(
        db_session,
        tenant,
        stop="1900",
        targets=[2500.0],
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    outcome = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2002, 1999, 2001))
    )
    assert outcome.status is RecommendationStatus.EXPIRED


@pytest.mark.asyncio
async def test_an_illegal_transition_is_recorded_not_raised(db_session: AsyncSession) -> None:
    """Crashing the tracker over one bad row stops every plan in the workspace."""
    tenant = await _tenant(db_session, email="t8@example.com", slug="t8")
    rec = await _recommendation(db_session, tenant, status=RecommendationStatus.EXPIRED)
    outcome = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2002, 1995, 1997))
    )
    assert outcome.changed is False
    assert outcome.reason == "illegal_transition"


# --- revisions ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transition_writes_its_reason(db_session: AsyncSession) -> None:
    """ "Invalidated" is half an answer, and not the half the user asked for."""
    tenant = await _tenant(db_session, email="t9@example.com", slug="t9")
    rec = await _recommendation(db_session, tenant)
    await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2002, 1995, 1997))
    )

    history = await revisions.list_revisions(db_session, tenant, rec.id)
    assert len(history) == 1
    assert history[0].reason == revisions.RevisionReason.INVALIDATION
    assert history[0].previous_status == RecommendationStatus.READY.value
    assert history[0].declared_status == RecommendationStatus.INVALIDATED.value


@pytest.mark.asyncio
async def test_revisions_are_numbered_and_ordered(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="t10@example.com", slug="t10")
    rec = await _recommendation(db_session, tenant, status=RecommendationStatus.FORMING)

    for status in (RecommendationStatus.READY, RecommendationStatus.INVALIDATED):
        previous = rec.status
        rec.status = status
        await db_session.flush()
        await revisions.record_revision(
            db_session,
            tenant,
            rec,
            reason=revisions.RevisionReason.MANUAL,
            previous_status=previous,
        )

    history = await revisions.list_revisions(db_session, tenant, rec.id)
    assert [r.seq for r in history] == [0, 1]


@pytest.mark.asyncio
async def test_the_row_is_the_live_state_and_the_revision_is_history(
    db_session: AsyncSession,
) -> None:
    """The trap this table creates, pinned.

    A card rendering its badge from the newest revision shows the status that
    was true when that revision was written — so a plan the tracker invalidated
    afterwards still reads READY, with the authority of the analysis behind it.
    """
    tenant = await _tenant(db_session, email="t11@example.com", slug="t11")
    rec = await _recommendation(db_session, tenant, status=RecommendationStatus.FORMING)
    await revisions.record_revision(
        db_session, tenant, rec, reason=revisions.RevisionReason.CREATED
    )

    # The tracker moves the row without writing a revision for this step.
    rec.status = RecommendationStatus.INVALIDATED
    await db_session.flush()

    newest = await revisions.latest_revision(db_session, tenant, rec.id)
    assert newest is not None
    assert newest.declared_status == RecommendationStatus.FORMING.value
    assert rec.status is RecommendationStatus.INVALIDATED
    assert newest.declared_status != rec.status.value


@pytest.mark.asyncio
async def test_an_unknown_revision_reason_is_refused(db_session: AsyncSession) -> None:
    """Free text turns the history into prose nothing can group or count."""
    tenant = await _tenant(db_session, email="t12@example.com", slug="t12")
    rec = await _recommendation(db_session, tenant)
    with pytest.raises(ValueError, match="unknown revision reason"):
        await revisions.record_revision(db_session, tenant, rec, reason="felt like it")


# --- the repository ----------------------------------------------------------


@pytest.mark.asyncio
async def test_open_statuses_derive_from_the_terminal_set(db_session: AsyncSession) -> None:
    """A new status joins the right side automatically instead of silently
    dropping out of every open-recommendation query."""
    assert RecommendationStatus.READY in repository.OPEN_STATUSES
    assert RecommendationStatus.EXPIRED not in repository.OPEN_STATUSES
    assert RecommendationStatus.TARGET_REACHED not in repository.OPEN_STATUSES


@pytest.mark.asyncio
async def test_a_row_from_another_workspace_is_invisible(db_session: AsyncSession) -> None:
    """Not an error — invisible. A caller must not be able to tell "does not
    exist" from "not yours", or the endpoint is an existence oracle."""
    owner = await _tenant(db_session, email="own@example.com", slug="own")
    rec = await _recommendation(db_session, owner)
    await db_session.commit()

    other = await _tenant(db_session, email="oth@example.com", slug="oth")
    assert await repository.get(db_session, other, rec.id) is None
    assert list(await repository.list_open(db_session, other)) == []


@pytest.mark.asyncio
async def test_revisions_are_workspace_scoped_too(db_session: AsyncSession) -> None:
    owner = await _tenant(db_session, email="own2@example.com", slug="own2")
    rec = await _recommendation(db_session, owner)
    await revisions.record_revision(db_session, owner, rec, reason=revisions.RevisionReason.CREATED)
    await db_session.commit()

    other = await _tenant(db_session, email="oth2@example.com", slug="oth2")
    assert list(await revisions.list_revisions(db_session, other, rec.id)) == []
    rows = (
        (
            await db_session.execute(
                select(RecommendationRevision).where(
                    RecommendationRevision.recommendation_id == rec.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
async def test_a_plan_nobody_took_can_still_be_recorded_as_working(
    db_session: AsyncSession,
) -> None:
    """The reason READY leads straight to both terminal outcomes.

    Leovee never executes, so nothing moves a plan to ACTIVE on its own — that
    status means the user reported taking it. If reaching a target required
    passing through ACTIVE, the learning loop would only ever see the trades
    someone bothered to log: the ones that looked good, which is a biased sample
    in the worst direction.
    """
    tenant = await _tenant(db_session, email="t13@example.com", slug="t13")
    rec = await _recommendation(db_session, tenant, status=RecommendationStatus.READY)

    outcome = await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2009, 1999, 2008))
    )
    assert outcome.status is RecommendationStatus.TARGET_REACHED
    # And nobody was ever recorded as being in it.
    assert rec.activated_at is None


# --- the cycle ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_cycle_evaluates_open_plans_across_workspaces(
    db_session: AsyncSession,
) -> None:
    from app.services.recommendations.worker import run_recommendation_tracker_cycle

    tenant = await _tenant(db_session, email="c1@example.com", slug="c1")
    await _recommendation(db_session, tenant, status=RecommendationStatus.READY)
    await db_session.commit()

    report = await run_recommendation_tracker_cycle(db_session)
    assert report.workspaces >= 1
    assert report.evaluated >= 1
    assert report.failures == []


@pytest.mark.asyncio
async def test_a_terminal_plan_is_not_re_evaluated(db_session: AsyncSession) -> None:
    """OPEN_STATUSES derives from the terminal set, so a finished plan drops out
    of the loop rather than being re-checked forever."""
    from app.services.recommendations.worker import run_recommendation_tracker_cycle

    tenant = await _tenant(db_session, email="c2@example.com", slug="c2")
    await _recommendation(db_session, tenant, status=RecommendationStatus.EXPIRED)
    await db_session.commit()

    report = await run_recommendation_tracker_cycle(db_session)
    assert report.evaluated == 0


@pytest.mark.asyncio
async def test_only_bars_after_the_plan_was_written_count(db_session: AsyncSession) -> None:
    """The level a plan was built around having been touched *before* it existed
    says nothing about the plan."""
    from app.services.recommendations.worker import _bars_since

    older = bar(ts=datetime(2026, 1, 1, tzinfo=UTC), open=2000, high=2001, low=1990, close=1995)
    newer = bar(ts=datetime(2026, 1, 2, tzinfo=UTC), open=2000, high=2001, low=1999, close=2000)
    kept = _bars_since([older, newer], datetime(2026, 1, 2, tzinfo=UTC))
    assert kept == [newer]


# --- the three axes ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_conditional_plan_cannot_be_valid_now(db_session: AsyncSession) -> None:
    """The one cross-layer rule, and it is not pedantry.

    "Conditional" means it waits for its stated trigger. Paired with valid_now
    it reads as an immediate plan to everything downstream while the user is
    told to wait — the two audiences then see different things about the same
    recommendation.
    """
    from app.services import recommendation_service

    tenant = await _tenant(db_session, email="ax1@example.com", slug="ax1")
    with pytest.raises(ValueError, match="waits for its stated trigger"):
        await recommendation_service.create_recommendation(
            db_session,
            tenant,
            symbol_code="XAUUSD",
            direction=RecommendationDirection.BUY,
            plan_type="CONDITIONAL",
            execution_state="VALID_NOW",
        )


@pytest.mark.asyncio
async def test_every_other_axis_pairing_is_legitimate(db_session: AsyncSession) -> None:
    """An immediate plan can be blocked; an anticipatory one can come live."""
    from app.services import recommendation_service

    tenant = await _tenant(db_session, email="ax2@example.com", slug="ax2")
    for plan_type, execution_state in (
        ("IMMEDIATE", "VALID_NOW"),
        ("ANTICIPATORY", "VALID_NOW"),
        ("ANTICIPATORY", "AWAITING_ACTIVATION"),
        ("CONDITIONAL", "AWAITING_ACTIVATION"),
    ):
        rec = await recommendation_service.create_recommendation(
            db_session,
            tenant,
            symbol_code="XAUUSD",
            direction=RecommendationDirection.BUY,
            plan_type=plan_type,
            execution_state=execution_state,
        )
        assert rec.plan_type == plan_type


@pytest.mark.asyncio
async def test_a_created_plan_carries_the_levels_the_tracker_needs(
    db_session: AsyncSession,
) -> None:
    """Before this the levels lived only inside evidence_json, so the tracker
    had no stop to watch and a recommendation could never resolve on its own."""
    from app.services import recommendation_service

    tenant = await _tenant(db_session, email="ax3@example.com", slug="ax3")
    rec = await recommendation_service.create_recommendation(
        db_session,
        tenant,
        symbol_code="XAUUSD",
        direction=RecommendationDirection.BUY,
        entry=Decimal("2000"),
        stop=Decimal("1996"),
        targets=[2008.0],
        timeframe="M15",
    )
    assert rec.entry == Decimal("2000")
    assert rec.stop == Decimal("1996")
    assert rec.targets_json == [2008.0]
    assert rec.timeframe == "M15"


@pytest.mark.asyncio
async def test_a_terminal_transition_reaches_the_learning_loop(
    db_session: AsyncSession,
) -> None:
    """The outcomes this loop produces are the ones nobody reported by hand.

    Setting the status directly would move the row and record the revision while
    leaving M8 blind — calibrating only on volunteered outcomes, which is to say
    the flattering half of the sample.
    """
    from app.models.learning import OutcomeRecord

    tenant = await _tenant(db_session, email="lh@example.com", slug="lh")
    rec = await _recommendation(db_session, tenant)
    await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2002, 1995, 1997))
    )

    outcomes = (
        (
            await db_session.execute(
                select(OutcomeRecord).where(OutcomeRecord.workspace_id == tenant.workspace_id)
            )
        )
        .scalars()
        .all()
    )
    assert outcomes, "the terminal transition never reached the learning pipeline"


@pytest.mark.asyncio
async def test_a_finished_plan_stops_reading_as_awaiting_activation(
    db_session: AsyncSession,
) -> None:
    """Leaving the execution axis at whatever creation set is how a finished
    plan keeps reading as pending forever."""
    tenant = await _tenant(db_session, email="es@example.com", slug="es")
    rec = await _recommendation(db_session, tenant, execution_state="AWAITING_ACTIVATION")
    await tracker.evaluate_recommendation(
        db_session, tenant, rec, bars=_bars((2000, 2002, 1995, 1997))
    )
    assert rec.execution_state == "INVALIDATED"

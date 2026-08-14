"""Re-evaluation: what raises a trigger, what is allowed to spend a cycle, and
what the cycle is allowed to change.

The ordering under test is the constitutional one:

    tracker notices → trigger recorded → fresh bundle → the same brain decides

Nothing here lets a detector edit a plan. That is the property, and the tests
that matter most are the ones asserting a trigger did *not* fire and a cycle did
*not* run — a re-evaluation costs a model call and rewrites a live
recommendation, so the expensive failure is firing too easily, not too rarely.
"""

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
from app.models.recommendation import Recommendation, RecommendationReevaluation
from app.services import market_data
from app.services.recommendations import reevaluation
from app.services.recommendations.reevaluation import (
    COOLDOWN,
    MAX_AUTOMATIC_CYCLES,
    CalendarEvent,
    CycleVerdict,
    LiveRead,
    ReevaluationReason,
    ReevaluationTrigger,
)
from app.tests.bars import bar
from app.tests.conftest import seed_user_org

MOMENT = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)


async def _tenant(session: AsyncSession, *, email: str, slug: str) -> TenantContext:
    user, _org, _member = await seed_user_org(session, email=email, slug=slug)
    ctx = await resolve_tenant_context(session, user.id)
    await bind_workspace_rls(session, ctx)
    return ctx


def _evidence(
    *,
    shape: str = "uptrend",
    bias: str = "BULLISH",
    pattern: str | None = "double_bottom",
    pattern_status: str = "forming",
    noise: float = 0.6,
) -> dict[str, Any]:
    """The engine bundle a plan was written with — its founding conditions."""
    return {
        "engines": {
            "structure": {"shape": shape},
            "mtf": {"trade_bias": bias},
            "geometry": (
                {"patterns": [{"pattern_type": pattern, "status": pattern_status}]}
                if pattern
                else {"patterns": []}
            ),
            "plan_sanity": {"context": {"noise": noise}},
        }
    }


async def _plan(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    status: RecommendationStatus = RecommendationStatus.READY,
    direction: RecommendationDirection = RecommendationDirection.BUY,
    entry: str = "2000",
    stop: str = "1996",
    evidence: dict[str, Any] | None = None,
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
        targets_json=[2008.0],
        timeframe="M15",
        plan_type="IMMEDIATE",
        execution_state="VALID_NOW",
        evidence_json=evidence if evidence is not None else _evidence(),
    )
    session.add(rec)
    await session.flush()
    return rec


def _bars(count: int = 60, *, wick: float = 0.6) -> list[OHLCBar]:
    return [
        bar(
            open=2000.0,
            high=2000.4 + wick / 2,
            low=2000.0 - wick / 2,
            close=2000.4,
            ts=MOMENT + timedelta(minutes=15 * i),
        )
        for i in range(count)
    ]


# --- detection ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_structure_that_flipped_against_the_plan_raises_a_trigger(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="rv1@example.com", slug="rv1")
    plan = await _plan(db_session, tenant, evidence=_evidence(shape="uptrend"))

    triggers = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), structure_shape="downtrend", now=MOMENT), symbol="XAUUSD"
    )
    assert [t.reason for t in triggers] == [ReevaluationReason.STRUCTURE_BREAK]


@pytest.mark.asyncio
async def test_a_structure_that_always_disagreed_is_not_news(db_session: AsyncSession) -> None:
    """The analysis knew, and took the trade anyway.

    A counter-trend scalp is a real setup. Re-litigating it every sweep would
    spend the whole lifetime cap arguing with a decision that was made on
    purpose, and the plan would never get to be right or wrong on its own terms.
    """
    tenant = await _tenant(db_session, email="rv2@example.com", slug="rv2")
    plan = await _plan(db_session, tenant, evidence=_evidence(shape="downtrend"))

    triggers = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), structure_shape="downtrend", now=MOMENT), symbol="XAUUSD"
    )
    assert triggers == []


@pytest.mark.asyncio
async def test_the_founding_pattern_resolving_either_way_raises_a_trigger(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="rv3@example.com", slug="rv3")
    plan = await _plan(db_session, tenant, evidence=_evidence(pattern_status="forming"))

    completed = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), pattern_status="completed", now=MOMENT), symbol="XAUUSD"
    )
    failed = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), pattern_status="invalidated", now=MOMENT), symbol="XAUUSD"
    )
    assert [t.reason for t in completed] == [ReevaluationReason.PATTERN_COMPLETED]
    assert [t.reason for t in failed] == [ReevaluationReason.PATTERN_FAILED]


@pytest.mark.asyncio
async def test_a_pattern_at_the_same_stage_is_not_a_trigger(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="rv4@example.com", slug="rv4")
    plan = await _plan(db_session, tenant, evidence=_evidence(pattern_status="completed"))

    triggers = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), pattern_status="completed", now=MOMENT), symbol="XAUUSD"
    )
    assert triggers == []


@pytest.mark.asyncio
async def test_noise_that_outgrew_the_stop_raises_the_measured_trigger(
    db_session: AsyncSession,
) -> None:
    """The live-price replacement for AiChart's spread trigger (ADR 0010).

    Nothing is assumed about execution. The question is whether the movement
    price gives back inside a candle has grown until the plan's own stop sits
    inside it — which is read off the candles.
    """
    tenant = await _tenant(db_session, email="rv5@example.com", slug="rv5")
    plan = await _plan(db_session, tenant, entry="2000", stop="1999", evidence=_evidence(noise=0.5))

    triggers = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(wick=2.0), now=MOMENT), symbol="XAUUSD"
    )
    assert [t.reason for t in triggers] == [ReevaluationReason.NOISE_OUTGREW_STOP]


@pytest.mark.asyncio
async def test_a_noisier_tape_the_stop_still_clears_is_worse_not_different(
    db_session: AsyncSession,
) -> None:
    """ "Worse" is not a reason to spend a model call."""
    tenant = await _tenant(db_session, email="rv6@example.com", slug="rv6")
    plan = await _plan(db_session, tenant, entry="2000", stop="1990", evidence=_evidence(noise=0.5))

    triggers = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(wick=2.0), now=MOMENT), symbol="XAUUSD"
    )
    assert triggers == []


@pytest.mark.asyncio
async def test_proximity_to_invalidation_alone_is_not_a_trigger(
    db_session: AsyncSession,
) -> None:
    """A plan is supposed to approach its levels.

    Without the conjunction this fires on every plan continuously, which is the
    same as having no trigger at all — except that it costs a model call each
    time.
    """
    tenant = await _tenant(db_session, email="rv7@example.com", slug="rv7")
    plan = await _plan(db_session, tenant, entry="2000", stop="2000.3")

    quiet = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), context_changed=False, now=MOMENT), symbol="XAUUSD"
    )
    changed = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), context_changed=True, now=MOMENT), symbol="XAUUSD"
    )
    assert ReevaluationReason.APPROACHING_INVALIDATION not in [t.reason for t in quiet]
    assert ReevaluationReason.APPROACHING_INVALIDATION in [t.reason for t in changed]


@pytest.mark.asyncio
async def test_an_absent_calendar_invents_nothing(db_session: AsyncSession) -> None:
    """No feed is not evidence that nothing is scheduled."""
    tenant = await _tenant(db_session, email="rv8@example.com", slug="rv8")
    plan = await _plan(db_session, tenant)

    triggers = reevaluation.detect_reevaluation_triggers(
        plan, LiveRead(bars=_bars(), now=MOMENT), symbol="XAUUSD"
    )
    assert ReevaluationReason.ECONOMIC_EVENT not in [t.reason for t in triggers]


@pytest.mark.asyncio
async def test_a_crowded_calendar_asks_for_one_cycle_not_four(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="rv9@example.com", slug="rv9")
    plan = await _plan(db_session, tenant)

    triggers = reevaluation.detect_reevaluation_triggers(
        plan,
        LiveRead(
            bars=_bars(),
            upcoming_events=[
                CalendarEvent("CPI", 5, "high"),
                CalendarEvent("Payrolls", 10, "high"),
                CalendarEvent("Speech", 20, "medium"),
            ],
            now=MOMENT,
        ),
        symbol="XAUUSD",
    )
    events = [t for t in triggers if t.reason is ReevaluationReason.ECONOMIC_EVENT]
    assert len(events) == 1


# --- admission ---------------------------------------------------------------


def _trigger(
    plan: Recommendation,
    *,
    reason: ReevaluationReason = ReevaluationReason.STRUCTURE_BREAK,
    at: datetime = MOMENT,
    key: str | None = None,
) -> ReevaluationTrigger:
    return ReevaluationTrigger(
        recommendation_id=plan.id,
        symbol="XAUUSD",
        reason=reason,
        detail="test",
        raised_at=at,
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_one_automatic_cycle_per_sweep(db_session: AsyncSession) -> None:
    """A sweep that noticed three things noticed one changed situation."""
    tenant = await _tenant(db_session, email="ra1@example.com", slug="ra1")
    plan = await _plan(db_session, tenant)

    result = await reevaluation.admit_triggers(
        db_session,
        tenant,
        [
            _trigger(plan, reason=ReevaluationReason.STRUCTURE_BREAK),
            _trigger(plan, reason=ReevaluationReason.PATTERN_FAILED),
            _trigger(plan, reason=ReevaluationReason.HIGHER_TIMEFRAME_REVERSAL),
        ],
    )
    assert len(result.admitted) == 1
    assert [why for _, why in result.suppressed] == [
        "one automatic cycle per sweep",
        "one automatic cycle per sweep",
    ]


@pytest.mark.asyncio
async def test_a_persistent_condition_is_one_request_not_one_per_tick(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="ra2@example.com", slug="ra2")
    plan = await _plan(db_session, tenant)

    first = await reevaluation.admit_triggers(db_session, tenant, [_trigger(plan, at=MOMENT)])
    soon = await reevaluation.admit_triggers(
        db_session, tenant, [_trigger(plan, at=MOMENT + timedelta(minutes=5))]
    )
    later = await reevaluation.admit_triggers(
        db_session, tenant, [_trigger(plan, at=MOMENT + COOLDOWN + timedelta(minutes=1))]
    )
    assert len(first.admitted) == 1
    assert [why for _, why in soon.suppressed] == ["within cooldown"]
    assert len(later.admitted) == 1


@pytest.mark.asyncio
async def test_a_plan_re_decided_to_the_cap_stops_being_argued_with(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="ra3@example.com", slug="ra3")
    plan = await _plan(db_session, tenant)

    at = MOMENT
    for _ in range(MAX_AUTOMATIC_CYCLES):
        admitted = await reevaluation.admit_triggers(db_session, tenant, [_trigger(plan, at=at)])
        assert len(admitted.admitted) == 1
        at += COOLDOWN + timedelta(minutes=1)

    over = await reevaluation.admit_triggers(db_session, tenant, [_trigger(plan, at=at)])
    assert [why for _, why in over.suppressed] == ["lifetime cap reached"]


@pytest.mark.asyncio
async def test_what_the_user_asked_for_is_never_rate_limited(db_session: AsyncSession) -> None:
    """The limits bound automatic spend. A person asking is not automatic."""
    tenant = await _tenant(db_session, email="ra4@example.com", slug="ra4")
    plan = await _plan(db_session, tenant)

    at = MOMENT
    for _ in range(MAX_AUTOMATIC_CYCLES):
        await reevaluation.admit_triggers(db_session, tenant, [_trigger(plan, at=at)])
        at += COOLDOWN + timedelta(minutes=1)

    asked = await reevaluation.admit_triggers(
        db_session,
        tenant,
        [_trigger(plan, reason=ReevaluationReason.USER_REQUEST, at=MOMENT, key="ask-1")],
    )
    assert len(asked.admitted) == 1


@pytest.mark.asyncio
async def test_a_suppressed_trigger_is_still_recorded(db_session: AsyncSession) -> None:
    """ "The structure broke — why did nothing happen" needs an answer."""
    tenant = await _tenant(db_session, email="ra5@example.com", slug="ra5")
    plan = await _plan(db_session, tenant)

    await reevaluation.admit_triggers(
        db_session,
        tenant,
        [
            _trigger(plan, reason=ReevaluationReason.STRUCTURE_BREAK),
            _trigger(plan, reason=ReevaluationReason.PATTERN_FAILED),
        ],
    )
    rows = await reevaluation.list_triggers(db_session, tenant, plan.id)
    outcomes = {row.reason: row.outcome for row in rows}
    assert outcomes[ReevaluationReason.PATTERN_FAILED.value] == "suppressed"
    assert rows[0].detail


# --- the comparison ----------------------------------------------------------


def test_a_float_artefact_is_not_a_plan_change() -> None:
    before = reevaluation.ComparableDecision(
        "BUY", "IMMEDIATE", 2000.0, 1996.0, (2008.0,), "VALID_NOW", None, 12
    )
    after = reevaluation.ComparableDecision(
        "BUY", "IMMEDIATE", 2000.0000000001, 1996.0, (2008.0,), "VALID_NOW", None, 12
    )
    changed, fields = reevaluation.decision_changed(before, after)
    assert not changed, fields


def test_a_decision_silent_about_validity_does_not_revise_it() -> None:
    """Silence is not "now null".

    Reading an omitted field as a change would revise every plan whose fresh
    decision simply did not mention it — a revision produced by the shape of the
    payload rather than by anything in the market.
    """
    before = reevaluation.ComparableDecision(
        "BUY", "IMMEDIATE", 2000.0, 1996.0, (2008.0,), "VALID_NOW", None, 12
    )
    after = reevaluation.ComparableDecision(
        "BUY", "IMMEDIATE", 2000.0, 1996.0, (2008.0,), "VALID_NOW", None, None
    )
    changed, _ = reevaluation.decision_changed(before, after)
    assert not changed


def test_a_degraded_run_is_not_a_comparable_decision() -> None:
    """An outage must not read as the agent standing by its call."""
    assert (
        reevaluation.comparable_from_decision(
            {"direction": "NO_TRADE", "degraded": True, "degraded_reason": "LLM_UNAVAILABLE"}
        )
        is None
    )


# --- the cycle ---------------------------------------------------------------


def _brain(decision: dict[str, Any]) -> Any:
    async def run(_symbol: str, _timeframe: str) -> dict[str, Any]:
        return {"decision": decision, "engines": {"structure": {"shape": "uptrend"}}}

    return run


@pytest.mark.asyncio
async def test_an_unchanged_decision_confirms_and_revises_nothing(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="rc1@example.com", slug="rc1")
    plan = await _plan(db_session, tenant)

    outcome = await reevaluation.run_reevaluation_cycle(
        db_session,
        tenant,
        plan,
        _trigger(plan),
        brain=_brain(
            {
                "direction": "BUY",
                "plan_type": "IMMEDIATE",
                "execution_state": "VALID_NOW",
                "levels": {"entry": 2000.0, "stop": 1996.0, "targets": [2008.0]},
            }
        ),
        now=MOMENT,
    )
    assert outcome.verdict is CycleVerdict.CONFIRMED
    assert outcome.changed_fields == []
    assert plan.entry == Decimal("2000")
    # Visible, though: "the agent looked again and stood by the plan" is
    # different information from "nobody looked".
    assert plan.last_evaluated_at is not None


@pytest.mark.asyncio
async def test_a_changed_decision_rewrites_the_plan_and_names_what_moved(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="rc2@example.com", slug="rc2")
    plan = await _plan(db_session, tenant)

    outcome = await reevaluation.run_reevaluation_cycle(
        db_session,
        tenant,
        plan,
        _trigger(plan),
        brain=_brain(
            {
                "direction": "BUY",
                "plan_type": "IMMEDIATE",
                "execution_state": "VALID_NOW",
                "levels": {"entry": 2001.0, "stop": 1997.5, "targets": [2010.0]},
            }
        ),
        now=MOMENT,
    )
    assert outcome.verdict is CycleVerdict.REVISED
    assert set(outcome.changed_fields) == {"entry", "stop", "targets"}
    assert plan.entry == Decimal("2001.0")
    assert plan.stop == Decimal("1997.5")
    assert plan.targets_json == [2010.0]


@pytest.mark.asyncio
async def test_the_cycle_never_sets_the_status(db_session: AsyncSession) -> None:
    """Status is the tracker's answer, read from price against the plan's levels.

    Two components with authority over one field is how a plan ends up
    invalidated by a re-evaluation while price never touched the stop.
    """
    tenant = await _tenant(db_session, email="rc3@example.com", slug="rc3")
    plan = await _plan(db_session, tenant, status=RecommendationStatus.READY)

    await reevaluation.run_reevaluation_cycle(
        db_session,
        tenant,
        plan,
        _trigger(plan),
        brain=_brain(
            {
                "direction": "SELL",
                "plan_type": "IMMEDIATE",
                "execution_state": "INVALIDATED",
                "levels": {"entry": 2001.0, "stop": 2005.0, "targets": [1990.0]},
            }
        ),
        now=MOMENT,
    )
    assert plan.status is RecommendationStatus.READY


@pytest.mark.asyncio
async def test_a_finished_plan_is_history_not_a_draft(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="rc4@example.com", slug="rc4")
    plan = await _plan(db_session, tenant, status=RecommendationStatus.INVALIDATED)

    outcome = await reevaluation.run_reevaluation_cycle(
        db_session,
        tenant,
        plan,
        _trigger(plan),
        brain=_brain({"direction": "BUY"}),
        now=MOMENT,
    )
    assert outcome.verdict is CycleVerdict.SKIPPED
    assert outcome.retryable is False


@pytest.mark.asyncio
async def test_a_degraded_cycle_leaves_the_plan_standing_and_stays_retryable(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="rc5@example.com", slug="rc5")
    plan = await _plan(db_session, tenant)

    outcome = await reevaluation.run_reevaluation_cycle(
        db_session,
        tenant,
        plan,
        _trigger(plan),
        brain=_brain(
            {"direction": "NO_TRADE", "degraded": True, "degraded_reason": "LLM_UNAVAILABLE"}
        ),
        now=MOMENT,
    )
    assert outcome.verdict is CycleVerdict.SKIPPED
    assert outcome.retryable is True
    assert plan.entry == Decimal("2000")


@pytest.mark.asyncio
async def test_the_ledger_is_scoped_to_its_workspace(db_session: AsyncSession) -> None:
    """The same guarantee as every other table: the database filters, not the code."""
    a = await _tenant(db_session, email="rz1@example.com", slug="rz1")
    plan = await _plan(db_session, a)
    await reevaluation.admit_triggers(db_session, a, [_trigger(plan)])
    await db_session.flush()

    b = await _tenant(db_session, email="rz2@example.com", slug="rz2")
    await bind_workspace_rls(db_session, b)
    rows = await db_session.execute(select(RecommendationReevaluation))
    assert rows.scalars().all() == []

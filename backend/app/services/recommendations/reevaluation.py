"""Re-evaluating an open plan: the trigger, the admission, and the cycle.

The tracker watches a live plan and notices things that *might* change it — the
structure it was built on breaks, the founding pattern resolves, the higher
frame turns, a release lands on the calendar, price creeps up on invalidation
while the picture around it changes.

What it does with that is the whole design. **It raises a trigger. It does not
decide, and it never touches a level:**

    tracker notices → trigger recorded → fresh evidence bundle
                    → the same brain decides → revision

A trigger is a *request for a decision cycle*, and the cycle's output is the only
thing allowed to change a plan. That ordering is what keeps one brain. If the
tracker could widen a stop "because the structure broke", there would be two
components deciding, and the second would be a heuristic with no evidence bundle
and no decision trace behind it — a plan changed by something that never looked
at the chart.

**Three properties are load-bearing, and each is enforced rather than trusted:**

1. **The same brain.** The cycle re-runs `run_analysis`, the entry point the
   original analysis used. A cheaper "re-check" path would be a second brain
   with its own habits, and the two would drift apart in exactly the cases that
   matter.
2. **A whole bundle.** The full evidence pipeline runs again. Deciding from the
   trigger's own payload — "the higher frame turned, so flip the direction" — is
   the heuristic this architecture exists to forbid.
3. **A revision only when something changed.** An unchanged decision records
   `confirmed` and writes no revision. Manufacturing an identical revision every
   sweep buries the real changes in a list of non-events.

**Automatic cycles are bounded.** A cycle costs a model call, so there is a
cooldown between them and a lifetime cap per plan. What the *user* asked for is
never rate limited: the limits exist to bound automatic spend, and a person
asking is not automatic.

**No spread trigger (ADR 0010).** AiChart re-decided when the spread widened past
twice what the plan was costed at. Leovee costs nothing at a spread, so the
honest equivalent is measured: when the movement price routinely gives back has
grown enough that the plan's own stop no longer clears it, the plan is a
different trade than the one that was published, and that is read off the
candles.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.engines.bar import OHLCBar
from app.engines.plan_sanity import measure_price_context
from app.models.enums import RecommendationDirection
from app.models.recommendation import Recommendation, RecommendationReevaluation
from app.observability.prometheus import reevaluation_triggers_total
from app.schemas.decision import ExecutionState
from app.services.recommendation_lifecycle import TERMINAL_RECOMMENDATION_STATUSES
from app.services.recommendations.revisions import (
    RevisionReason,
    lock_recommendation,
    record_revision,
)

logger = structlog.get_logger(__name__)

__all__ = [
    "COOLDOWN",
    "MAX_AUTOMATIC_CYCLES",
    "ReevaluationReason",
    "ReevaluationTrigger",
    "LiveRead",
    "FoundingConditions",
    "founding_conditions",
    "CycleVerdict",
    "detect_reevaluation_triggers",
    "claim_key",
    "admit_triggers",
    "record_trigger",
    "list_triggers",
    "ComparableDecision",
    "comparable_from_recommendation",
    "comparable_from_decision",
    "decision_changed",
    "CycleResult",
    "run_reevaluation_cycle",
    "evidence_fingerprint",
    "planned_noise_for",
]

#: Smallest gap between automatic cycles for one plan.
#:
#: A cycle costs a model call. Without a floor, a plan sitting next to a
#: structure that keeps re-breaking would re-decide on every sweep and produce a
#: stream of near-identical revisions — noise for the reader, cost for nobody.
COOLDOWN = timedelta(minutes=15)

#: Most automatic cycles one plan may cause in its whole life.
#:
#: A plan that has been re-decided six times is not being refined, it is being
#: argued with. Past that the honest move is to let it reach its own conclusion.
MAX_AUTOMATIC_CYCLES = 6

#: Minutes inside which a calendar release counts as imminent.
EVENT_IMMINENT_MINUTES = 30

#: How close to invalidation counts as "approaching", in ATR.
INVALIDATION_BAND_ATR = 0.5

#: How much the measured noise floor must grow before the plan is a different
#: trade. Doubling, not drifting: below that the plan is worse, above it the
#: stop that was written no longer describes the same risk.
NOISE_GROWTH_MULTIPLE = 2.0


class ReevaluationReason(StrEnum):
    """Why a fresh decision cycle is warranted. A closed vocabulary — free text
    here turns the ledger into prose that nothing can group or count."""

    #: The structure the plan was built on broke against it.
    STRUCTURE_BREAK = "structure_break"
    #: The founding pattern finished forming.
    PATTERN_COMPLETED = "pattern_completed"
    #: The founding pattern failed or was invalidated.
    PATTERN_FAILED = "pattern_failed"
    #: The higher frame reversed against the plan.
    HIGHER_TIMEFRAME_REVERSAL = "higher_timeframe_reversal"
    #: Movement price gives back within a candle has grown past the plan's stop.
    #: The measured replacement for AiChart's spread trigger (ADR 0010).
    NOISE_OUTGREW_STOP = "noise_outgrew_stop"
    #: A calendar release is imminent.
    ECONOMIC_EVENT = "economic_event"
    #: Price is near invalidation and the surrounding picture changed.
    APPROACHING_INVALIDATION = "approaching_invalidation_changed_context"
    #: The research agent returned a verdict.
    RESEARCH_VERDICT = "research_verdict"
    #: The user asked.
    USER_REQUEST = "user_request"


#: What the *user* asked for is never rate limited. The limits bound automatic
#: spend; a person asking is not automatic, and making them wait out a cooldown
#: they cannot see is the product refusing a question for reasons of its own.
EXEMPT_FROM_LIMITS: frozenset[ReevaluationReason] = frozenset(
    {ReevaluationReason.USER_REQUEST, ReevaluationReason.RESEARCH_VERDICT}
)


class CycleVerdict(StrEnum):
    CONFIRMED = "confirmed"
    REVISED = "revised"
    INVALIDATED = "invalidated"
    SKIPPED = "skipped"


class TriggerOutcome(StrEnum):
    REQUESTED = "requested"
    SUPPRESSED = "suppressed"


@dataclass(frozen=True, slots=True)
class ReevaluationTrigger:
    recommendation_id: uuid.UUID
    symbol: str
    reason: ReevaluationReason
    #: Readable why, stored with the trigger.
    detail: str
    #: Which component noticed. Never the decider.
    source: str = "tracker"
    #: The revision in force when it was raised, so a stale trigger — one about a
    #: plan that has since changed — is recognisable instead of being applied to
    #: a plan it was never about.
    revision_seq: int | None = None
    raised_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: Stable producer identity, when the noticing component has one.
    idempotency_key: str | None = None

    @property
    def exempt(self) -> bool:
        return self.reason in EXEMPT_FROM_LIMITS

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": str(self.recommendation_id),
            "symbol": self.symbol,
            "reason": self.reason.value,
            "detail": self.detail,
            "source": self.source,
            "revision_seq": self.revision_seq,
            "raised_at": self.raised_at.isoformat(),
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    title: str
    minutes_away: float
    impact: str


@dataclass(frozen=True, slots=True)
class LiveRead:
    """What the deterministic engines see *right now*. All of it optional.

    A missing input produces no trigger — never an invented one. No calendar
    provider means no `economic_event`, which is correct: the absence of a feed
    is not evidence that nothing is scheduled, and manufacturing a trigger from
    it would re-decide plans on a fiction.
    """

    bars: list[OHLCBar] = field(default_factory=list)
    #: Structure shape now: uptrend / downtrend / range / unknown.
    structure_shape: str | None = None
    #: The founding pattern's stage now, when the detector still sees it.
    pattern_status: str | None = None
    higher_timeframe_bias: str | None = None
    upcoming_events: list[CalendarEvent] = field(default_factory=list)
    #: True when something in the surrounding evidence moved. Proximity to the
    #: stop alone is not news — a plan is *supposed* to approach its levels.
    context_changed: bool = False
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class FoundingConditions:
    """What the plan was built on, read back from the evidence it was written with.

    No new columns: the recommendation already stores the whole engine bundle in
    ``evidence_json``, and that bundle *is* the founding state. Re-deriving it
    from today's candles instead would compare the market to itself and conclude
    nothing ever changes — the comparison has to be against what the plan was
    actually made from.
    """

    structure_shape: str | None = None
    higher_timeframe_bias: str | None = None
    founding_pattern: str | None = None
    pattern_status: str | None = None
    noise: float | None = None


def founding_conditions(recommendation: Recommendation) -> FoundingConditions:
    engines = (recommendation.evidence_json or {}).get("engines") or {}
    if not isinstance(engines, dict):
        return FoundingConditions()

    def branch(name: str) -> dict[str, Any]:
        value = engines.get(name)
        return value if isinstance(value, dict) else {}

    structure = branch("structure")
    mtf = branch("mtf")
    geometry = branch("geometry")
    sanity = branch("plan_sanity")

    patterns = geometry.get("patterns") or []
    leading: dict[str, Any] = patterns[0] if patterns and isinstance(patterns[0], dict) else {}
    raw_context = sanity.get("context")
    context: dict[str, Any] = raw_context if isinstance(raw_context, dict) else {}

    return FoundingConditions(
        structure_shape=structure.get("shape"),
        higher_timeframe_bias=mtf.get("trade_bias"),
        founding_pattern=leading.get("pattern_type"),
        pattern_status=leading.get("status"),
        noise=_as_float(context.get("noise")),
    )


def _cooldown_bucket(moment: datetime) -> int:
    """Which cooldown window a moment falls in.

    Used in dedupe keys so a condition that persists across sweeps produces one
    trigger per window rather than one per sweep — the condition has not changed,
    only the clock has.
    """
    return int(moment.timestamp() // COOLDOWN.total_seconds())


def _against(direction: RecommendationDirection, bias: str | None) -> bool:
    """Does this bias point against the plan?

    A break that *confirms* the plan is not news. Re-deciding on agreement burns
    a model call to be told what the plan already says.
    """
    if bias is None:
        return False
    lowered = bias.lower()
    if direction is RecommendationDirection.BUY:
        return lowered in ("down", "downtrend", "bearish")
    if direction is RecommendationDirection.SELL:
        return lowered in ("up", "uptrend", "bullish")
    return False


def detect_reevaluation_triggers(
    recommendation: Recommendation,
    live: LiveRead,
    *,
    symbol: str,
    founding: FoundingConditions | None = None,
) -> list[ReevaluationTrigger]:
    """What changed *since the plan was written*. Pure: no reads, no writes.

    The comparison is against the founding bundle, not against the previous
    sweep. Comparing today's read to yesterday's would report drift as news and
    would say nothing at all about a plan whose premise dissolved slowly.

    An empty list is the common and correct answer — most sweeps change nothing,
    and a detector that finds something every time is measuring its own
    sensitivity rather than the market.
    """
    was = founding or founding_conditions(recommendation)
    moment = live.now or datetime.now(UTC)
    triggers: list[ReevaluationTrigger] = []

    def raise_(reason: ReevaluationReason, detail: str, key: str | None = None) -> None:
        triggers.append(
            ReevaluationTrigger(
                recommendation_id=recommendation.id,
                symbol=symbol,
                reason=reason,
                detail=detail,
                source="tracker",
                revision_seq=None,
                raised_at=moment,
                idempotency_key=key,
            )
        )

    # Structure. The shape has to have *moved* and the new one has to point
    # against the plan. A structure that always disagreed with it is not news —
    # the analysis knew that and took the trade anyway, which is a counter-trend
    # scalp, not a mistake to re-litigate every sweep.
    if (
        live.structure_shape is not None
        and was.structure_shape is not None
        and live.structure_shape != was.structure_shape
        and _against(recommendation.direction, live.structure_shape)
    ):
        raise_(
            ReevaluationReason.STRUCTURE_BREAK,
            f"{symbol}: تحوّل الهيكل من {was.structure_shape} إلى {live.structure_shape} "
            "ضد اتجاه الخطة.",
            f"structure:{was.structure_shape}->{live.structure_shape}",
        )

    if was.founding_pattern and live.pattern_status and live.pattern_status != was.pattern_status:
        stage = live.pattern_status.lower()
        if stage in ("completed", "confirmed"):
            raise_(
                ReevaluationReason.PATTERN_COMPLETED,
                f"{symbol}: اكتمل {was.founding_pattern} الذي بُنيت عليه الخطة.",
                f"pattern:{was.founding_pattern}:{stage}",
            )
        elif stage in ("failed", "invalidated"):
            raise_(
                ReevaluationReason.PATTERN_FAILED,
                f"{symbol}: فشل {was.founding_pattern} الذي بُنيت عليه الخطة.",
                f"pattern:{was.founding_pattern}:{stage}",
            )

    # The higher frame turning against the plan. Compared to what it was when the
    # plan was written, for the same reason as the structure check: a plan taken
    # against H4 was taken against H4 on purpose.
    if live.higher_timeframe_bias != was.higher_timeframe_bias and _against(
        recommendation.direction, live.higher_timeframe_bias
    ):
        raise_(
            ReevaluationReason.HIGHER_TIMEFRAME_REVERSAL,
            f"{symbol}: انعكس الفريم الأعلى ضد الخطة.",
            f"htf:{live.higher_timeframe_bias}:{_cooldown_bucket(moment)}",
        )

    noise_trigger = _noise_outgrew_stop(recommendation, live, was, symbol=symbol, moment=moment)
    if noise_trigger is not None:
        triggers.append(noise_trigger)

    for event in live.upcoming_events:
        if event.minutes_away <= EVENT_IMMINENT_MINUTES:
            raise_(
                ReevaluationReason.ECONOMIC_EVENT,
                f"{symbol}: {event.title} بعد {max(0, round(event.minutes_away))} دقيقة "
                f"({event.impact}).",
                f"event:{event.title}:{event.impact}:{_cooldown_bucket(moment)}",
            )
            # One is enough to ask for one cycle. A calendar with four releases
            # in the next hour is one reason to look again, not four.
            break

    proximity = _approaching_invalidation(recommendation, live)
    if proximity is not None:
        raise_(
            ReevaluationReason.APPROACHING_INVALIDATION,
            proximity,
            f"invalidation-band:{INVALIDATION_BAND_ATR}atr:{_cooldown_bucket(moment)}",
        )

    return triggers


def _noise_outgrew_stop(
    recommendation: Recommendation,
    live: LiveRead,
    was: FoundingConditions,
    *,
    symbol: str,
    moment: datetime,
) -> ReevaluationTrigger | None:
    """Has the tape become noisier than the plan's stop was written for?

    The measured replacement for AiChart's spread trigger. The question is the
    same — "is this still the trade that was published?" — but the answer comes
    from the candles: when the movement price routinely gives back inside a
    candle has doubled, a stop that comfortably cleared it now sits inside it,
    and the plan's risk is no longer the risk the reader was told about.
    """
    if recommendation.entry is None or recommendation.stop is None:
        return None
    if not live.bars or was.noise is None or was.noise <= 0:
        return None

    context = measure_price_context(live.bars, atr=0.0)
    if context.noise <= 0:
        return None
    growth = context.noise / was.noise
    if growth < NOISE_GROWTH_MULTIPLE:
        return None

    stop_distance = abs(float(recommendation.entry) - float(recommendation.stop))
    if stop_distance > context.noise:
        # Noisier, but the stop still clears it. The plan is worse, not
        # different — and "worse" is not a reason to spend a model call.
        return None

    return ReevaluationTrigger(
        recommendation_id=recommendation.id,
        symbol=symbol,
        reason=ReevaluationReason.NOISE_OUTGREW_STOP,
        detail=(
            f"{symbol}: الحركة التي يعيدها السعر داخل الشمعة صارت {growth:.1f}× ما "
            f"كُتب عليه الوقف، والوقف الآن داخلها."
        ),
        source="tracker",
        raised_at=moment,
        idempotency_key=f"noise:{growth:.1f}:{_cooldown_bucket(moment)}",
    )


def _approaching_invalidation(recommendation: Recommendation, live: LiveRead) -> str | None:
    """Near the stop *and* the picture changed.

    Proximity alone is not a trigger: a plan is supposed to approach its stop or
    its target, and re-deciding every time price moves toward a level would
    re-decide every plan continuously. The conjunction is the signal.
    """
    if not live.context_changed or not live.bars or recommendation.stop is None:
        return None
    policy_atr = _atr_of(live.bars)
    if policy_atr <= 0:
        return None
    distance = abs(live.bars[-1].close - float(recommendation.stop))
    if distance > policy_atr * INVALIDATION_BAND_ATR:
        return None
    return f"السعر ضمن {INVALIDATION_BAND_ATR} ATR من مستوى الإبطال، والأدلة المحيطة تغيّرت."


def _atr_of(bars: list[OHLCBar]) -> float:
    from app.engines.primitives.pivots import geometry_atr

    return geometry_atr(bars)


def planned_noise_for(bars: list[OHLCBar]) -> float:
    """The noise floor to record against a plan when it is written.

    Stored so a later sweep can ask whether the *tape* changed, rather than
    comparing today's noise to today's noise and always concluding nothing moved.
    """
    if not bars:
        return 0.0
    return measure_price_context(bars, atr=0.0).noise


# --- admission --------------------------------------------------------------


def claim_key(trigger: ReevaluationTrigger) -> str:
    """The idempotency key a trigger claims when it asks for a cycle.

    Built from the revision it was raised against plus its reason, so the same
    condition seen twice at the same revision is one claim. Exempt reasons carry
    the producer's own identity instead of a time bucket: a user asking twice is
    two questions, and collapsing them would silently drop the second.
    """
    base = f"{trigger.revision_seq or 0}:{trigger.reason.value}"
    if trigger.exempt:
        tail = trigger.idempotency_key or f"{trigger.raised_at.timestamp():.0f}"
        return f"{base}:{tail}"[:200]
    tail = trigger.idempotency_key or f"window:{_cooldown_bucket(trigger.raised_at)}"
    return f"{base}:{tail}"[:200]


@dataclass(slots=True)
class AdmissionResult:
    admitted: list[ReevaluationTrigger] = field(default_factory=list)
    suppressed: list[tuple[ReevaluationTrigger, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": [t.reason.value for t in self.admitted],
            "suppressed": [{"reason": t.reason.value, "why": why} for t, why in self.suppressed],
        }


async def _write_trigger_row(
    session: AsyncSession,
    tenant: TenantContext,
    trigger: ReevaluationTrigger,
    *,
    outcome: str,
    dedupe_key: str,
    completed_at: datetime | None = None,
    evidence_hash: str | None = None,
    decision: dict[str, Any] | None = None,
) -> bool:
    """Insert one ledger row, or do nothing if that claim is already taken.

    Returns whether *this* call wrote it. That return is the admission decision:
    two overlapping sweeps race to the same key and exactly one of them gets
    True, so exactly one pays for the model call.
    """
    await bind_workspace_rls(session, tenant)
    statement = (
        pg_insert(RecommendationReevaluation)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant.tenant_id,
            workspace_id=tenant.workspace_id,
            recommendation_id=trigger.recommendation_id,
            reason=trigger.reason.value,
            detail=trigger.detail,
            source=trigger.source,
            revision_seq=trigger.revision_seq,
            outcome=outcome,
            raised_at=trigger.raised_at,
            completed_at=completed_at,
            dedupe_key=dedupe_key,
            evidence_hash=evidence_hash,
            trigger_json=trigger.to_dict(),
            decision_json=decision or {},
        )
        .on_conflict_do_nothing(constraint="uq_recommendation_reevaluation_dedupe")
        .returning(RecommendationReevaluation.id)
    )
    written = await session.scalar(statement)
    await session.flush()
    if written is not None:
        reevaluation_triggers_total.labels(trigger.reason.value, outcome).inc()
    return written is not None


async def record_trigger(
    session: AsyncSession,
    tenant: TenantContext,
    trigger: ReevaluationTrigger,
    *,
    outcome: TriggerOutcome,
    why: str | None = None,
) -> bool:
    """Record a trigger, admitted or not.

    A suppressed trigger is not a non-event. It is the answer to "the structure
    broke — why did nothing happen", and a ledger holding only the cycles that
    ran cannot give it.
    """
    if outcome is TriggerOutcome.REQUESTED:
        return await _write_trigger_row(
            session,
            tenant,
            trigger,
            outcome=outcome.value,
            dedupe_key=claim_key(trigger),
        )
    # Suppressions are never collapsed with each other: each one is a distinct
    # moment the condition was seen and declined, and merging them would hide
    # how often that happened.
    stamp = f"{trigger.raised_at.timestamp():.0f}"
    key = f"suppressed:{trigger.revision_seq or 0}:{trigger.reason.value}:{stamp}"
    return await _write_trigger_row(
        session,
        tenant,
        trigger,
        outcome=outcome.value,
        dedupe_key=key[:200],
        decision={"why": why} if why else {},
    )


async def admit_triggers(
    session: AsyncSession,
    tenant: TenantContext,
    triggers: Sequence[ReevaluationTrigger],
) -> AdmissionResult:
    """Which detected triggers may actually start a cycle.

    Four limits, and each has a different justification:

    - **one automatic cycle per sweep**, because a sweep that noticed three
      things has noticed one changed situation, and three model calls would
      decide the same bundle three times;
    - **a cooldown**, so a persistent condition is one request, not one per tick;
    - **a lifetime cap**, because a plan re-decided six times is being argued
      with rather than refined;
    - **de-duplication in the database**, which is the only one that holds under
      concurrency — the other three are read-then-decide and two workers can pass
      all of them at once.

    User-initiated reasons bypass the first three and keep the fourth: a person
    asking twice deserves two answers, but a double-submitted request does not.
    """
    result = AdmissionResult()
    if not triggers:
        return result

    history = await _automatic_history(session, tenant, triggers[0].recommendation_id)
    used = len(history)
    last_raised = history[0] if history else None
    admitted_now = 0

    for trigger in triggers:
        if trigger.exempt:
            if await record_trigger(session, tenant, trigger, outcome=TriggerOutcome.REQUESTED):
                result.admitted.append(trigger)
            else:
                result.suppressed.append((trigger, "duplicate"))
            continue

        why: str | None = None
        if used + admitted_now >= MAX_AUTOMATIC_CYCLES:
            why = "lifetime cap reached"
        elif last_raised is not None and trigger.raised_at - last_raised < COOLDOWN:
            why = "within cooldown"
        elif admitted_now >= 1:
            why = "one automatic cycle per sweep"

        if why is not None:
            await record_trigger(
                session, tenant, trigger, outcome=TriggerOutcome.SUPPRESSED, why=why
            )
            result.suppressed.append((trigger, why))
            continue

        if await record_trigger(session, tenant, trigger, outcome=TriggerOutcome.REQUESTED):
            result.admitted.append(trigger)
            admitted_now += 1
        else:
            result.suppressed.append((trigger, "duplicate"))

    return result


async def _automatic_history(
    session: AsyncSession, tenant: TenantContext, recommendation_id: uuid.UUID
) -> list[datetime]:
    """When automatic cycles were requested for this plan, newest first."""
    await bind_workspace_rls(session, tenant)
    exempt = [reason.value for reason in EXEMPT_FROM_LIMITS]
    rows = await session.execute(
        select(RecommendationReevaluation.raised_at)
        .where(
            RecommendationReevaluation.recommendation_id == recommendation_id,
            RecommendationReevaluation.outcome == TriggerOutcome.REQUESTED.value,
            RecommendationReevaluation.reason.notin_(exempt),
        )
        .order_by(RecommendationReevaluation.raised_at.desc())
        .limit(50)
    )
    return [row if row.tzinfo else row.replace(tzinfo=UTC) for row in rows.scalars().all()]


async def list_triggers(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation_id: uuid.UUID,
    *,
    limit: int = 50,
) -> Sequence[RecommendationReevaluation]:
    """The whole ledger for one plan, newest first."""
    await bind_workspace_rls(session, tenant)
    rows = await session.execute(
        select(RecommendationReevaluation)
        .where(RecommendationReevaluation.recommendation_id == recommendation_id)
        .order_by(RecommendationReevaluation.raised_at.desc())
        .limit(limit)
    )
    return rows.scalars().all()


# --- did the decision actually change? --------------------------------------


@dataclass(frozen=True, slots=True)
class ComparableDecision:
    """The plan fields whose change is worth a new revision.

    Everything else — wording, a confidence that drifted by a hundredth, a
    reordered reason list — is the same plan described again. Treating those as
    changes writes a revision on every sweep and makes the revision number
    meaningless, which costs the reader the one signal that told them something
    real had happened.
    """

    direction: str
    plan_type: str | None
    entry: float | None
    stop: float | None
    targets: tuple[float, ...]
    execution_state: str | None
    activation_condition: str | None
    validity_candles: int | None


def _same_price(a: float | None, b: float | None) -> bool:
    """Price equality at instrument scale — a float artefact is not a change."""
    if a is None or b is None:
        return a == b
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= scale * 1e-6


def comparable_from_recommendation(row: Recommendation) -> ComparableDecision:
    return ComparableDecision(
        direction=row.direction.value,
        plan_type=row.plan_type,
        entry=float(row.entry) if row.entry is not None else None,
        stop=float(row.stop) if row.stop is not None else None,
        targets=tuple(float(t) for t in (row.targets_json or []) if isinstance(t, int | float)),
        execution_state=row.execution_state,
        activation_condition=row.activation_condition,
        validity_candles=None,
    )


def comparable_from_decision(decision: dict[str, Any]) -> ComparableDecision | None:
    """Read a fresh decision payload, or None when it did not produce a plan.

    None is not "unchanged". A degraded run is an operational blocker, and the
    previous decision stands until the plan can actually be re-examined —
    treating a failed cycle as confirmation would let an outage read as the agent
    standing by its call.
    """
    direction = decision.get("direction")
    levels = decision.get("levels")
    if direction not in ("BUY", "SELL") or not isinstance(levels, dict):
        return None
    targets = levels.get("targets") or []
    return ComparableDecision(
        direction=str(direction),
        plan_type=decision.get("plan_type"),
        entry=_as_float(levels.get("entry")),
        stop=_as_float(levels.get("stop")),
        targets=tuple(float(t) for t in targets if isinstance(t, int | float)),
        execution_state=decision.get("execution_state"),
        activation_condition=decision.get("condition"),
        validity_candles=decision.get("validity_candles"),
    )


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def decision_changed(
    before: ComparableDecision, after: ComparableDecision
) -> tuple[bool, list[str]]:
    """Which fields moved, if any."""
    fields: list[str] = []
    if before.direction != after.direction:
        fields.append("direction")
    if before.plan_type != after.plan_type:
        fields.append("plan_type")
    if not _same_price(before.entry, after.entry):
        fields.append("entry")
    if not _same_price(before.stop, after.stop):
        fields.append("stop")
    if len(before.targets) != len(after.targets) or any(
        not _same_price(a, b) for a, b in zip(before.targets, after.targets, strict=False)
    ):
        fields.append("targets")
    if before.execution_state != after.execution_state:
        fields.append("execution_state")
    if (before.activation_condition or "") != (after.activation_condition or ""):
        fields.append("activation_condition")
    # Only when the fresh decision states one: a payload that omits validity is
    # silent about it, and reading silence as "now null" would revise every plan
    # whose new decision simply did not mention the field.
    if after.validity_candles is not None and before.validity_candles != after.validity_candles:
        fields.append("validity")
    return bool(fields), fields


def evidence_fingerprint(evidence: dict[str, Any]) -> str:
    """One hash function for evidence bundles, everywhere.

    Key-sorted, so the same bundle built in a different order hashes the same.
    Two hash functions for one object is how a cycle's recorded hash ends up
    disagreeing with the revision's for identical evidence.
    """
    payload = json.dumps(evidence, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- the cycle --------------------------------------------------------------


@dataclass(slots=True)
class CycleResult:
    recommendation_id: uuid.UUID
    verdict: CycleVerdict
    detail: str
    reason: ReevaluationReason
    changed_fields: list[str] = field(default_factory=list)
    evidence_hash: str | None = None
    #: A retryable skip leaves the claim open for the next sweep. A permanent one
    #: closes it: re-asking a question whose answer cannot change is pure cost.
    retryable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": str(self.recommendation_id),
            "verdict": self.verdict.value,
            "detail": self.detail,
            "reason": self.reason.value,
            "changed_fields": list(self.changed_fields),
            "evidence_hash": self.evidence_hash,
        }


#: How the brain is reached. Injected so a test exercises the real comparison
#: rather than a comparison against a stub of itself.
BrainFn = Callable[[str, str], Awaitable[dict[str, Any]]]


async def run_reevaluation_cycle(
    session: AsyncSession,
    tenant: TenantContext,
    recommendation: Recommendation,
    trigger: ReevaluationTrigger,
    *,
    brain: BrainFn,
    now: datetime | None = None,
) -> CycleResult:
    """Consume one admitted trigger: fresh bundle, same brain, compare, record.

    The recommendation row is locked for the whole cycle, so a tracker
    transition and a re-evaluation cannot both read the same status and both
    conclude their transition is legal from it.
    """
    moment = now or datetime.now(UTC)

    def skip(detail: str, *, retryable: bool = True) -> CycleResult:
        return CycleResult(
            recommendation_id=recommendation.id,
            verdict=CycleVerdict.SKIPPED,
            detail=detail,
            reason=trigger.reason,
            retryable=retryable,
        )

    await lock_recommendation(session, recommendation.id)

    if recommendation.status in TERMINAL_RECOMMENDATION_STATUSES:
        # A finished plan is history, not a draft. Re-deciding it would produce a
        # revision the state machine correctly refuses, and the refusal would be
        # logged as a fault rather than as the plan simply being over.
        outcome = skip(f"terminal status {recommendation.status.value}", retryable=False)
        await _record_cycle(session, tenant, trigger, outcome, moment=moment)
        return outcome

    fresh = await brain(trigger.symbol, recommendation.timeframe or "")
    after = comparable_from_decision(fresh.get("decision") or {})
    if after is None:
        # An operational blocker is not a verdict about the plan. Saying nothing
        # is correct — the previous decision stands until it can actually be
        # re-examined, and recording "confirmed" here would let an outage read as
        # the agent standing by its call.
        degraded = (fresh.get("decision") or {}).get("degraded_reason")
        return skip(f"no decision to compare ({degraded or 'unknown'})")

    before = comparable_from_recommendation(recommendation)
    changed, fields = decision_changed(before, after)
    evidence_hash = evidence_fingerprint(fresh.get("engines") or {})

    if not changed:
        outcome = CycleResult(
            recommendation_id=recommendation.id,
            verdict=CycleVerdict.CONFIRMED,
            detail=(f"{trigger.symbol}: أُعيد التقييم بعد {trigger.reason.value} والقرار لم يتغيّر."),
            reason=trigger.reason,
            evidence_hash=evidence_hash,
        )
        recommendation.last_evaluated_at = moment
        await session.flush()
        # A confirmation is a real outcome and must be visible: "the market moved
        # and the agent looked again and stood by the plan" is different
        # information from "nobody looked", and a reader who cannot tell them
        # apart cannot trust either.
        await record_revision(
            session,
            tenant,
            recommendation,
            reason=RevisionReason.REEVALUATION,
            changes={"verdict": CycleVerdict.CONFIRMED.value, "trigger": trigger.reason.value},
            note=outcome.detail,
        )
        await _record_cycle(session, tenant, trigger, outcome, moment=moment)
        return outcome

    previous_status = recommendation.status
    _apply(recommendation, after, moment=moment)
    verdict = (
        CycleVerdict.INVALIDATED
        if after.execution_state == ExecutionState.INVALIDATED.value
        else CycleVerdict.REVISED
    )
    outcome = CycleResult(
        recommendation_id=recommendation.id,
        verdict=verdict,
        detail=(
            f"{trigger.symbol}: أُعيد التقييم بعد {trigger.reason.value} — تغيّر {'، '.join(fields)}."
        ),
        reason=trigger.reason,
        changed_fields=fields,
        evidence_hash=evidence_hash,
    )
    await session.flush()
    await record_revision(
        session,
        tenant,
        recommendation,
        reason=RevisionReason.REEVALUATION,
        previous_status=previous_status,
        changes={"verdict": verdict.value, "fields": fields, "trigger": trigger.reason.value},
        note=outcome.detail,
    )
    await _record_cycle(session, tenant, trigger, outcome, moment=moment)
    return outcome


def _apply(recommendation: Recommendation, after: ComparableDecision, *, moment: datetime) -> None:
    """Write the new plan onto the row.

    Levels and plan type only. **The status is not touched here** — whether a
    plan is invalidated, expired or ready is the tracker's answer, read from
    price against the plan's own levels, and letting a re-evaluation set it too
    would give two components authority over one field.
    """
    recommendation.direction = RecommendationDirection(after.direction)
    recommendation.plan_type = after.plan_type
    recommendation.execution_state = after.execution_state
    recommendation.activation_condition = after.activation_condition
    if after.entry is not None:
        recommendation.entry = Decimal(str(after.entry))
    if after.stop is not None:
        recommendation.stop = Decimal(str(after.stop))
    if after.targets:
        recommendation.targets_json = [float(t) for t in after.targets]
    recommendation.last_evaluated_at = moment


async def _record_cycle(
    session: AsyncSession,
    tenant: TenantContext,
    trigger: ReevaluationTrigger,
    outcome: CycleResult,
    *,
    moment: datetime,
) -> None:
    """Write what the cycle concluded, and close its claim.

    A retryable skip deliberately leaves the claim open: the condition was real
    and nothing was decided, so the next sweep should be able to try again rather
    than finding the question already marked answered.
    """
    await _write_trigger_row(
        session,
        tenant,
        trigger,
        outcome=outcome.verdict.value,
        dedupe_key=f"{claim_key(trigger)}:{outcome.verdict.value}"[:200],
        completed_at=moment,
        evidence_hash=outcome.evidence_hash,
        decision=outcome.to_dict(),
    )
    if outcome.verdict is CycleVerdict.SKIPPED and outcome.retryable:
        return
    await bind_workspace_rls(session, tenant)
    await session.execute(
        update(RecommendationReevaluation)
        .where(
            RecommendationReevaluation.recommendation_id == trigger.recommendation_id,
            RecommendationReevaluation.dedupe_key == claim_key(trigger),
            RecommendationReevaluation.outcome == TriggerOutcome.REQUESTED.value,
            RecommendationReevaluation.completed_at.is_(None),
        )
        .values(completed_at=moment)
    )
    await session.flush()

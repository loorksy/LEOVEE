"""The cycle that walks every workspace's open plans.

**One failing workspace must not stop the others.** A single unreadable
activation rule, a missing symbol, a transient database error — each is a
one-tenant problem, and letting it abort the loop turns it into an
every-tenant outage where nobody's plans are tracked. The failure is recorded
per workspace and the cycle moves on.

**Candles are loaded once per symbol, not once per plan.** A workspace with
thirty open gold plans is thirty evaluations against the same bars, and fetching
them thirty times turns a cheap loop into a load problem that only appears in
production.

**Each plan is evaluated against the bars since it was written**, not against
the latest price. A stop that was hit and recovered from is still a stop that
was hit — reading only the current price reports a trade that is winning when it
was closed out two bars ago.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.symbols import DEFAULT_SYMBOL
from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.timeframes import DEFAULT_SERIES_TIMEFRAME, MTF_CONTEXT_STACK
from app.engines.bar import OHLCBar, bars_from_candles
from app.engines.geometry import run_geometry_engine
from app.engines.mtf import run_mtf_engine
from app.engines.structure import run_structure_engine
from app.models.enums import Timeframe
from app.models.recommendation import Recommendation
from app.models.symbol import Symbol
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.services import market_data
from app.services.recommendations import reevaluation, repository
from app.services.recommendations.tracker import evaluate_recommendation

logger = structlog.get_logger(__name__)

__all__ = [
    "TrackerCycleReport",
    "run_recommendation_tracker_cycle",
    "ReevaluationSweepReport",
    "run_reevaluation_sweep",
]

#: Enough to cover the life of any open scalp plan. Beyond this the plan has
#: expired anyway, so loading more bars buys nothing.
TRACKER_BARS = 500


@dataclass(slots=True)
class TrackerCycleReport:
    workspaces: int = 0
    evaluated: int = 0
    changed: int = 0
    #: Per-workspace failures, kept rather than raised: one tenant's problem
    #: must not read as the tracker being down.
    failures: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspaces": self.workspaces,
            "evaluated": self.evaluated,
            "changed": self.changed,
            "failures": list(self.failures),
        }


async def _context_for(session: AsyncSession, workspace: Workspace) -> TenantContext | None:
    member = await session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id).limit(1)
    )
    if member is None:
        # A workspace with no members has nobody to answer for it; skipping is
        # correct and silent, not an error to report every minute.
        return None
    return await resolve_tenant_context(session, member.user_id)


async def _bars_for(
    session: AsyncSession, symbol_id: Any, timeframe: Timeframe, cache: dict[Any, list[OHLCBar]]
) -> list[OHLCBar]:
    key = (symbol_id, timeframe.value)
    if key not in cache:
        candles = await market_data.load_recent_candles(
            session, symbol_id, timeframe=timeframe, count=TRACKER_BARS
        )
        cache[key] = bars_from_candles(candles)
    return cache[key]


def _bars_since(bars: list[OHLCBar], created_at: datetime) -> list[OHLCBar]:
    """Only what happened after the plan was written.

    Evaluating against earlier bars would find the stop "hit" by price action
    that predates the recommendation — the level the plan was built around
    having been touched before it existed says nothing about it.
    """
    since = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return [bar for bar in bars if bar.ts >= since]


async def run_recommendation_tracker_cycle(
    session: AsyncSession, *, now: datetime | None = None
) -> TrackerCycleReport:
    """Advance every open plan in every workspace."""
    moment = now or datetime.now(UTC)
    report = TrackerCycleReport()

    workspaces = list((await session.execute(select(Workspace))).scalars().all())
    for workspace in workspaces:
        report.workspaces += 1
        try:
            tenant = await _context_for(session, workspace)
            if tenant is None:
                continue
            open_plans = await repository.list_open(session, tenant)
            cache: dict[Any, list[OHLCBar]] = {}
            for plan in open_plans:
                bars = await _bars_for(session, plan.symbol_id, _timeframe_of(plan), cache)
                outcome = await evaluate_recommendation(
                    session,
                    tenant,
                    plan,
                    bars=_bars_since(bars, plan.created_at),
                    now=moment,
                )
                report.evaluated += 1
                if outcome.changed:
                    report.changed += 1
        except Exception as exc:  # noqa: BLE001 — one tenant, not all of them
            logger.warning(
                "tracker_cycle_workspace_failed",
                workspace_id=str(workspace.id),
                error=str(exc)[:200],
            )
            report.failures.append({"workspace_id": str(workspace.id), "error": str(exc)[:200]})
            # The session may be poisoned by the failed statement; roll back to
            # a usable state or every remaining workspace fails too.
            await session.rollback()

    return report


def _timeframe_of(plan: Recommendation) -> Timeframe:
    """The frame the plan was made on, or the default series frame.

    A plan tracked on the wrong frame is checked against candles it was never
    sized for: an M1 stop evaluated on H4 bars is "hit" by a wick that an M1
    trader would have seen as three separate, survivable pokes.
    """
    if plan.timeframe:
        try:
            return Timeframe(plan.timeframe)
        except ValueError:
            logger.warning("tracker_unknown_timeframe", timeframe=plan.timeframe)
    return DEFAULT_SERIES_TIMEFRAME


@dataclass(slots=True)
class ReevaluationSweepReport:
    workspaces: int = 0
    plans: int = 0
    detected: int = 0
    admitted: int = 0
    suppressed: int = 0
    cycles: dict[str, int] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspaces": self.workspaces,
            "plans": self.plans,
            "detected": self.detected,
            "admitted": self.admitted,
            "suppressed": self.suppressed,
            "cycles": dict(self.cycles),
            "failures": list(self.failures),
        }


async def _default_brain(
    session: AsyncSession, tenant: TenantContext
) -> Callable[[str, str], Awaitable[dict[str, Any]]]:
    """The same entry point a user's analysis uses.

    Deliberately not a cheaper re-check path. A second decision route would be a
    second brain with its own habits, and the two would disagree exactly where
    it matters — a plan revised by the cheap path and defended by the real one.
    """
    from app.services.analysis_service import run_analysis

    async def brain(symbol: str, timeframe: str) -> dict[str, Any]:
        frame = DEFAULT_SERIES_TIMEFRAME
        if timeframe:
            try:
                frame = Timeframe(timeframe)
            except ValueError:
                logger.warning("reevaluation_unknown_timeframe", timeframe=timeframe)
        return await run_analysis(session, tenant, symbol=symbol, timeframe=frame)

    return brain


async def run_reevaluation_sweep(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    brain_factory: Callable[
        [AsyncSession, TenantContext], Awaitable[Callable[[str, str], Awaitable[dict[str, Any]]]]
    ] = _default_brain,
) -> ReevaluationSweepReport:
    """Notice, admit, and re-decide — for every open plan in every workspace.

    Separate from the tracker cycle on purpose. The tracker answers questions
    about *price against the plan's own levels*: cheap, deterministic, and worth
    running every few minutes. This one may spend a model call, so it runs on the
    cooldown's cadence and its own admission rules bound what it spends.
    """
    moment = now or datetime.now(UTC)
    report = ReevaluationSweepReport()

    workspaces = list((await session.execute(select(Workspace))).scalars().all())
    for workspace in workspaces:
        report.workspaces += 1
        try:
            tenant = await _context_for(session, workspace)
            if tenant is None:
                continue
            brain = await brain_factory(session, tenant)
            cache: dict[Any, list[OHLCBar]] = {}
            for plan in await repository.list_open(session, tenant):
                report.plans += 1
                await _reevaluate_one(
                    session, tenant, plan, brain=brain, cache=cache, moment=moment, report=report
                )
        except Exception as exc:  # noqa: BLE001 — one tenant, not all of them
            logger.warning(
                "reevaluation_sweep_workspace_failed",
                workspace_id=str(workspace.id),
                error=str(exc)[:200],
            )
            report.failures.append({"workspace_id": str(workspace.id), "error": str(exc)[:200]})
            await session.rollback()

    return report


async def _reevaluate_one(
    session: AsyncSession,
    tenant: TenantContext,
    plan: Recommendation,
    *,
    brain: Callable[[str, str], Awaitable[dict[str, Any]]],
    cache: dict[Any, list[OHLCBar]],
    moment: datetime,
    report: ReevaluationSweepReport,
) -> None:
    symbol_row = await session.get(Symbol, plan.symbol_id)
    symbol = symbol_row.code if symbol_row is not None else DEFAULT_SYMBOL
    bars = await _bars_for(session, plan.symbol_id, _timeframe_of(plan), cache)
    if not bars:
        return

    frame = _timeframe_of(plan)
    ladder = {
        tf.value: await _bars_for(session, plan.symbol_id, tf, cache) for tf in MTF_CONTEXT_STACK
    }
    ladder[frame.value] = bars
    live = _live_read(bars, ladder, frame, moment=moment)
    triggers = reevaluation.detect_reevaluation_triggers(plan, live, symbol=symbol)
    report.detected += len(triggers)
    if not triggers:
        return

    admission = await reevaluation.admit_triggers(session, tenant, triggers)
    report.admitted += len(admission.admitted)
    report.suppressed += len(admission.suppressed)

    for trigger in admission.admitted:
        outcome = await reevaluation.run_reevaluation_cycle(
            session, tenant, plan, trigger, brain=brain, now=moment
        )
        report.cycles[outcome.verdict.value] = report.cycles.get(outcome.verdict.value, 0) + 1


def _live_read(
    bars: list[OHLCBar],
    ladder: dict[str, list[OHLCBar]],
    frame: Timeframe,
    *,
    moment: datetime,
) -> reevaluation.LiveRead:
    """Today's deterministic read of the same engines the plan was built from.

    The higher-frame bias needs the whole ladder, not the plan's own frame: an
    MTF read given one series reports that series agreeing with itself, which
    would make `higher_timeframe_reversal` unraisable — a trigger that exists in
    the vocabulary and can never fire is worse than one that is absent, because
    its silence reads as evidence.

    Only the engines here — no calendar, no `context_changed`. Those come from
    feeds this sweep does not have, and inventing them would raise triggers on
    events nobody observed, which is the one failure a re-evaluation must not
    have: it spends a model call and revises a real plan.
    """
    structure = run_structure_engine(bars)
    geometry = run_geometry_engine(bars)
    patterns = geometry.get("patterns") or []
    leading = patterns[0] if patterns and isinstance(patterns[0], dict) else {}
    mtf = run_mtf_engine(ladder, decision_timeframe=frame.value)
    return reevaluation.LiveRead(
        bars=bars,
        structure_shape=structure.get("shape"),
        pattern_status=leading.get("status"),
        higher_timeframe_bias=mtf.get("trade_bias"),
        now=moment,
    )

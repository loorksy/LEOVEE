"""Learning-loop read tools: strategy stats, calibration, case memory, DNA.

Mixed scope, and the split is doctrine rather than convenience:

**Workspace tools** read the tenant's own record — strategy statistics,
statistical support, calibration bins, trading DNA, lessons, memories and the
performance summary. Every one of them reads through the RLS-bound session on
the context; none accepts a workspace/tenant/user argument, so a caller cannot
widen its own access by passing a different id (there is no such parameter to
pass), and dispatch refuses them on an unbound context.

**Platform tools** read `market_cases`, which is shared market fact in the same
class as candles: "gold has looked like this 47 times before" is identical for
every workspace and carries no tenant columns. What is *not* shared is how a
given workspace's own plans fared — that lives in `strategy_stats` behind RLS.
No tool here blends the two into one number; the ADR on the cases package says
they must never be added together, and keeping them in separate tools is how
that survives contact with a model that would happily average them.

Everything is a read, every list is bounded, and the honesty gates the backing
modules enforce (support floors, minimum samples, similarity floors) come back
in the payload rather than being smoothed over: a thin sample says so.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.registry import ToolContext, ToolSpec
from app.core.symbols import require_instrument
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.core.timeframes import ACTIVE_TIMEFRAMES, ANALYSIS_WINDOW_BARS
from app.engines.bar import bars_from_candles
from app.models.enums import RecommendationStatus, Timeframe
from app.models.learning import OutcomeRecord, StrategyStat
from app.models.memory import Lesson
from app.models.recommendation import Recommendation
from app.models.trade import Trade
from app.services import market_data, memory_service, performance_service
from app.services.learning.outcome_recorder import OutcomeKind
from app.services.memory.cases import (
    MIN_SIMILARITY,
    MIN_STATS_SAMPLE,
    CaseFingerprint,
    find_similar_cases,
    fingerprint_at,
)
from app.services.memory.cases.fingerprint import MIN_CANDLES
from app.services.strategies.matching_keys import (
    ANY,
    UNKNOWN,
    Classification,
    classification_from_evidence,
)
from app.services.strategies.support import SupportReason, assess_support
from app.services.strategies.thresholds import MIN_OUTCOMES_FOR_SUPPORT
from app.services.trading_dna import (
    DnaMetric,
    EvidenceBundle,
    PlanRecord,
    TradeRecord,
    compute_metrics,
    derive_persona,
)

__all__ = ["TOOLS"]

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

#: Semantic memory search keeps the service's own default; the cap stays low
#: because every hit carries free-form content into the prompt.
SEARCH_DEFAULT_K = 10
SEARCH_MAX_K = 50

#: How many of the most recent closed plans (and reported trades) the trading
#: DNA reads. A window rather than the whole table: the profile describes how
#: the reader trades *now*, and the payload stays bounded however old the
#: workspace grows.
DNA_EVIDENCE_WINDOW = 100


def _tenant(context: ToolContext) -> TenantContext:
    """Narrow the optional tenant. Dispatch already refused unbound contexts."""
    tenant = context.tenant
    assert tenant is not None
    return tenant


def _limit(arguments: dict[str, Any], default: int = DEFAULT_LIMIT) -> int:
    raw = int(arguments.get("limit", default))
    return max(1, min(raw, MAX_LIMIT))


def _timeframe(arguments: dict[str, Any], default: Timeframe = Timeframe.M15) -> Timeframe:
    # Mirrors the registry's private helper rather than importing it — a copy
    # that drifts shows up in review; a cross-module import of privates does not.
    raw = arguments.get("timeframe")
    if raw is None:
        return default
    timeframe = Timeframe(str(raw).upper())
    if timeframe not in ACTIVE_TIMEFRAMES:
        raise ValueError(
            f"{timeframe.value} is not stored. Available: "
            f"{', '.join(tf.value for tf in ACTIVE_TIMEFRAMES)}"
        )
    return timeframe


def _as_float(value: Any) -> float | None:
    """A float when the source actually holds a number; None otherwise.

    Never a default: an absent measurement reported as 0.0 is exactly the kind
    of invented value the DNA module's gates exist to keep out.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    return None


# --- workspace: strategy statistics ------------------------------------------


def _stat_to_dict(row: StrategyStat) -> dict[str, Any]:
    return {
        "strategy_code": row.strategy_code,
        "setup_type": row.setup_type,
        "regime_bucket": row.regime_bucket,
        "session_bucket": row.session_bucket,
        "volatility_bucket": row.volatility_bucket,
        "occurrences": row.occurrences,
        "wins": row.wins,
        # Observed averages as stored — no derived rate here. Grading what the
        # sample supports is get_strategy_support's job, with its intervals.
        "avg_r": float(row.avg_r),
        "profit_factor": float(row.profit_factor) if row.profit_factor is not None else None,
        "expectancy": float(row.expectancy) if row.expectancy is not None else None,
        "suspended": row.suspended,
        "updated_at": row.updated_at.isoformat(),
    }


async def _get_strategy_stats(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """This workspace's own bucket counters, exactly as the pipeline wrote them."""
    tenant = _tenant(context)
    await bind_workspace_rls(context.session, tenant)
    query = select(StrategyStat)
    raw_code = arguments.get("strategy_code")
    if raw_code:
        query = query.where(StrategyStat.strategy_code == str(raw_code).strip().lower())
    query = query.order_by(
        StrategyStat.occurrences.desc(),
        StrategyStat.strategy_code,
        StrategyStat.setup_type,
        StrategyStat.regime_bucket,
        StrategyStat.session_bucket,
        StrategyStat.volatility_bucket,
    ).limit(_limit(arguments))
    rows = list((await context.session.execute(query)).scalars().all())
    return {"count": len(rows), "stats": [_stat_to_dict(row) for row in rows]}


# --- workspace: statistical support -------------------------------------------

#: One fixed sentence per reason code, for the model reading the payload. The
#: support module returns codes and numbers; these are the tool's rendering of
#: them, and the honest one for a thin record is the first entry.
_SUPPORT_INTERPRETATION: dict[str, str] = {
    SupportReason.NO_HISTORY.value: (
        "No closed outcomes match this classification: direct analysis, no statistical support."
    ),
    SupportReason.PROVISIONAL.value: (
        "A few real outcomes, below the support floor: still direct analysis; "
        "the counts travel with it but cannot grade it."
    ),
    SupportReason.SUSPENDED.value: (
        "The matching bucket is suspended: its record argues against relying "
        "on it, not merely thinly for it."
    ),
    SupportReason.AGGREGATED.value: (
        "The numbers come from a wider bucket than the exact classification; "
        "aggregated_over names the dimensions averaged across."
    ),
    SupportReason.PRESENT.value: (
        "The workspace's own record backs this exact bucket at the stated level."
    ),
}


def _classification_from_arguments(arguments: dict[str, Any]) -> Classification:
    raw_code = str(arguments.get("strategy_code") or "").strip()
    if not raw_code:
        raise ValueError("strategy_code is required")

    def bucket(name: str) -> str:
        raw = arguments.get(name)
        return str(raw).strip().upper() if raw else ANY

    return Classification(
        strategy_code=raw_code.lower(),
        setup_type=bucket("setup_type"),
        regime_bucket=bucket("regime_bucket"),
        session_bucket=bucket("session_bucket"),
        volatility_bucket=bucket("volatility_bucket"),
    )


async def _get_strategy_support(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    classification = _classification_from_arguments(arguments)
    support = await assess_support(context.session, tenant, classification)
    return {
        "classification": classification.to_dict(),
        "support": support.to_dict(),
        "min_outcomes_for_support": MIN_OUTCOMES_FOR_SUPPORT,
        "interpretation": _SUPPORT_INTERPRETATION[support.reason.value],
    }


# --- workspace: calibration ---------------------------------------------------


async def _get_calibration(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """The confidence bins the learning pipeline fills, plus their totals.

    Raw counts, deliberately: a per-bin accuracy computed from three rows would
    be a rate the sample cannot support, and the reader of these numbers is a
    model that would quote it.
    """
    tenant = _tenant(context)
    bins = await memory_service.list_calibration_curve(context.session, tenant)
    ordered = sorted(bins, key=lambda item: item["bin_lower"])
    return {
        "bin_count": len(ordered),
        "bins": ordered,
        "predicted_total": sum(item["predicted_count"] for item in ordered),
        "realized_success_total": sum(item["realized_success_count"] for item in ordered),
    }


# --- workspace: trading DNA ---------------------------------------------------


async def _load_dna_bundle(session: AsyncSession) -> EvidenceBundle:
    """The evidence the DNA modules read, from the RLS-bound session.

    Plans come from PLAN-kind outcome records joined to their recommendation
    rows; a record whose plan row is gone cannot be described and is skipped
    rather than padded. Trades are the self-reported journal — behaviour, never
    accuracy (D4) — and only the follow-through metric reads them.
    """
    outcome_rows = list(
        (
            await session.execute(
                select(OutcomeRecord)
                .where(
                    OutcomeRecord.kind == OutcomeKind.PLAN.value,
                    OutcomeRecord.recommendation_id.is_not(None),
                )
                .order_by(OutcomeRecord.recorded_at.desc(), OutcomeRecord.id.desc())
                .limit(DNA_EVIDENCE_WINDOW)
            )
        )
        .scalars()
        .all()
    )
    rec_ids = {row.recommendation_id for row in outcome_rows if row.recommendation_id is not None}
    recommendations: dict[uuid.UUID, Recommendation] = {}
    if rec_ids:
        result = await session.execute(select(Recommendation).where(Recommendation.id.in_(rec_ids)))
        recommendations = {rec.id: rec for rec in result.scalars().all()}

    plans: list[PlanRecord] = []
    for row in outcome_rows:
        rec = recommendations.get(row.recommendation_id) if row.recommendation_id else None
        if rec is None:
            continue
        classification = classification_from_evidence(rec.evidence_json)
        # UNKNOWN means the session could not be derived — a data gap, not a
        # preference, so it must not become a label in the session distribution.
        session_bucket = (
            None if classification.session_bucket == UNKNOWN else classification.session_bucket
        )
        facts = row.facts_json or {}
        plans.append(
            PlanRecord(
                recommendation_id=str(rec.id),
                outcome_id=str(row.id),
                direction=rec.direction.value,
                outcome=row.outcome,
                success=row.outcome == RecommendationStatus.TARGET_REACHED.value,
                timeframe=rec.timeframe,
                session_bucket=session_bucket,
                confidence_stated=_as_float(rec.confidence_calibrated),
                r_multiple=_as_float(row.r_multiple),
                # Reported only when the outcome recorded them; absent stays
                # absent and the metric says insufficient, per the module.
                mae_r=_as_float(facts.get("mae_r")),
                mfe_r=_as_float(facts.get("mfe_r")),
                created_at=rec.created_at,
                closed_at=row.recorded_at,
            )
        )

    trade_rows = list(
        (
            await session.execute(
                select(Trade)
                .order_by(Trade.created_at.desc(), Trade.id.desc())
                .limit(DNA_EVIDENCE_WINDOW)
            )
        )
        .scalars()
        .all()
    )
    trade_r: dict[uuid.UUID, Decimal | None] = {}
    if trade_rows:
        trade_outcomes = await session.execute(
            select(OutcomeRecord).where(
                OutcomeRecord.kind == OutcomeKind.TRADE.value,
                OutcomeRecord.trade_id.in_([trade.id for trade in trade_rows]),
            )
        )
        trade_r = {
            record.trade_id: record.r_multiple
            for record in trade_outcomes.scalars().all()
            if record.trade_id is not None
        }
    trades = tuple(
        TradeRecord(
            trade_id=str(trade.id),
            recommendation_id=(
                str(trade.recommendation_id) if trade.recommendation_id is not None else None
            ),
            r_multiple=_as_float(trade_r.get(trade.id)),
        )
        for trade in trade_rows
    )
    return EvidenceBundle(plans=tuple(plans), trades=trades)


def _metric_payload(metric: DnaMetric) -> dict[str, Any]:
    """The metric exactly as the module reports it, minus the row-id tables.

    Statuses, values, sample sizes and gates travel verbatim — an insufficient
    metric stays insufficient-with-reason. Only the per-row id lists are folded
    to counts: up to a hundred UUIDs per metric is a table dumped into a
    prompt, and the trace exists for the profile surface, not for the model.
    """
    payload = metric.to_dict()
    references = payload.pop("references")
    payload["evidence_rows"] = {key: len(ids) for key, ids in references.items()}
    return payload


async def _get_trading_dna(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    await bind_workspace_rls(context.session, tenant)
    bundle = await _load_dna_bundle(context.session)
    persona = derive_persona(bundle)
    metrics = compute_metrics(bundle)
    return {
        "persona": persona.to_dict(),
        "metrics": [_metric_payload(metric) for metric in metrics],
        "evidence_window": {
            "closed_plans": len(bundle.plans),
            "reported_trades": len(bundle.trades),
            "max_rows": DNA_EVIDENCE_WINDOW,
        },
    }


# --- workspace: lessons and memories ------------------------------------------


def _lesson_to_dict(row: Lesson) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "statement": row.statement,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "conditions": row.conditions_json,
        "low_sample": bool(row.conditions_json.get("LOW_SAMPLE", False)),
        "supporting_episodes": len(row.supporting_episode_ids),
        "user_edited": row.user_edited,
        "decay_at": row.decay_at.isoformat() if row.decay_at is not None else None,
        "created_at": row.created_at.isoformat(),
    }


async def _list_lessons(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    await bind_workspace_rls(context.session, tenant)
    result = await context.session.execute(
        select(Lesson)
        .where(Lesson.archived_at.is_(None))
        .order_by(Lesson.created_at.desc(), Lesson.id.desc())
        .limit(_limit(arguments))
    )
    rows = list(result.scalars().all())
    return {"count": len(rows), "lessons": [_lesson_to_dict(row) for row in rows]}


async def _search_memories(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    k = max(1, min(int(arguments.get("k", SEARCH_DEFAULT_K)), SEARCH_MAX_K))
    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    memories = await memory_service.retrieve_memories_hybrid(
        context.session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol=spec.symbol,
        query=query,
        limit=k,
    )
    return {"count": len(memories), "memories": memories}


async def _get_performance_summary(
    context: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    tenant = _tenant(context)
    return await performance_service.workspace_performance_summary(context.session, tenant)


# --- platform: market case memory ---------------------------------------------


def _direction(arguments: dict[str, Any]) -> str:
    direction = str(arguments.get("direction") or "").strip().lower()
    if direction not in ("buy", "sell"):
        raise ValueError("direction must be 'buy' or 'sell'")
    return direction


async def _fingerprint_probe(
    context: ToolContext, arguments: dict[str, Any]
) -> tuple[str, uuid.UUID, Timeframe, CaseFingerprint]:
    """Fingerprint the current stored window — the probe every case is scored against."""
    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    timeframe = _timeframe(arguments)
    symbol_row = await market_data.get_or_create_symbol(context.session, spec.symbol)
    candles = await market_data.load_recent_candles(
        context.session, symbol_row.id, timeframe=timeframe, count=ANALYSIS_WINDOW_BARS
    )
    fingerprint = fingerprint_at(bars_from_candles(candles))
    if fingerprint is None:
        raise ValueError(
            f"not enough stored {timeframe.value} candles to fingerprint the current "
            f"window (need at least {MIN_CANDLES})"
        )
    return spec.symbol, symbol_row.id, timeframe, fingerprint


async def _find_similar_cases(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Shared market history only — never joined with any workspace's own record."""
    direction = _direction(arguments)
    symbol, symbol_id, timeframe, fingerprint = await _fingerprint_probe(context, arguments)
    result = await find_similar_cases(
        context.session,
        symbol_id=symbol_id,
        timeframe=timeframe.value,
        fingerprint=fingerprint,
        direction=direction,
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe.value,
        "min_similarity": MIN_SIMILARITY,
        "probe_fingerprint": fingerprint.to_dict(),
        # to_dict bounds the case list itself; below MIN_STATS_SAMPLE the stats
        # carry counts and withhold rates, exactly as the module computed them.
        **result.to_dict(),
    }


async def _get_case_outcome_stats(
    context: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    direction = _direction(arguments)
    symbol, symbol_id, timeframe, fingerprint = await _fingerprint_probe(context, arguments)
    result = await find_similar_cases(
        context.session,
        symbol_id=symbol_id,
        timeframe=timeframe.value,
        fingerprint=fingerprint,
        direction=direction,
    )
    stats = result.stats
    return {
        "symbol": symbol,
        "timeframe": timeframe.value,
        "direction": direction,
        "candidates_considered": result.candidates_considered,
        "matched_cases": len(result.cases),
        "min_similarity": MIN_SIMILARITY,
        "min_stats_sample": MIN_STATS_SAMPLE,
        #: False means the rates above are withheld, not zero.
        "sufficient": stats.sufficient,
        "stats": stats.to_dict(),
    }


# --- declarations -------------------------------------------------------------

_LIMIT_PARAM: dict[str, Any] = {
    "type": "integer",
    "description": f"Rows to return, 1-{MAX_LIMIT}. Default {DEFAULT_LIMIT}.",
}
_SYMBOL_PARAM: dict[str, Any] = {
    "type": "string",
    "description": "Instrument. Only XAUUSD is available.",
}
_TIMEFRAME_PARAM: dict[str, Any] = {
    "type": "string",
    "enum": [tf.value for tf in ACTIVE_TIMEFRAMES],
    "description": "Timeframe of the window to fingerprint. Defaults to M15.",
}
_DIRECTION_PARAM: dict[str, Any] = {
    "type": "string",
    "enum": ["buy", "sell"],
    "description": "Which side's forward outcomes to read.",
}
_BUCKET_DESCRIPTION = (
    "Optional; omit to aggregate across this dimension deliberately (reads as ANY)."
)

_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}}

_CLASSIFICATION_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy_code": {
            "type": "string",
            "description": "The strategy bucket code, e.g. structure_uptrend_trending_m15.",
        },
        "setup_type": {"type": "string", "description": _BUCKET_DESCRIPTION},
        "regime_bucket": {"type": "string", "description": _BUCKET_DESCRIPTION},
        "session_bucket": {"type": "string", "description": _BUCKET_DESCRIPTION},
        "volatility_bucket": {"type": "string", "description": _BUCKET_DESCRIPTION},
    },
    "required": ["strategy_code"],
}

_CASE_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": _SYMBOL_PARAM,
        "timeframe": _TIMEFRAME_PARAM,
        "direction": _DIRECTION_PARAM,
    },
    "required": ["direction"],
}

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_strategy_stats",
        description=(
            "This workspace's own strategy statistics: per-bucket occurrences, wins "
            "and average R exactly as the learning pipeline recorded them, most-used "
            "buckets first. Workspace record only — market case memory is separate."
        ),
        parameters={
            "type": "object",
            "properties": {
                "strategy_code": {
                    "type": "string",
                    "description": "Optional filter to one strategy bucket code.",
                },
                "limit": _LIMIT_PARAM,
            },
        },
        handler=_get_strategy_stats,
        scope="workspace",
    ),
    ToolSpec(
        name="get_strategy_support",
        description=(
            "How much this workspace's own record backs a classification, walking the "
            "read ladder from the exact bucket outward. Honest about thin samples: "
            "'none' and 'provisional' mean direct analysis with no statistical support."
        ),
        parameters=_CLASSIFICATION_PARAMS,
        handler=_get_strategy_support,
        scope="workspace",
    ),
    ToolSpec(
        name="get_calibration",
        description=(
            "The workspace's confidence-calibration bins: stated-confidence ranges "
            "with predicted and realized counts, as raw counts."
        ),
        parameters=_NO_ARGS,
        handler=_get_calibration,
        scope="workspace",
    ),
    ToolSpec(
        name="get_trading_dna",
        description=(
            "The reader's behavioural profile from their own closed plans and reported "
            "trades: persona plus ten metrics, each supported or explicitly "
            "insufficient with its sample size and required floor."
        ),
        parameters=_NO_ARGS,
        handler=_get_trading_dna,
        scope="workspace",
    ),
    ToolSpec(
        name="list_lessons",
        description="Learned lessons in this workspace, newest first, unarchived only.",
        parameters={"type": "object", "properties": {"limit": _LIMIT_PARAM}},
        handler=_list_lessons,
        scope="workspace",
    ),
    ToolSpec(
        name="search_memories",
        description=(
            "Semantic search over this workspace's agent memories for one symbol: "
            "keyword and vector hits merged, at most 50 items."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search query."},
                "symbol": _SYMBOL_PARAM,
                "k": {
                    "type": "integer",
                    "description": f"1-{SEARCH_MAX_K} items, default {SEARCH_DEFAULT_K}.",
                },
            },
            "required": ["query"],
        },
        handler=_search_memories,
        scope="workspace",
    ),
    ToolSpec(
        name="get_performance_summary",
        description=(
            "The workspace performance summary: recommendation status counts, trade "
            "ideas, outcome records and the calibration totals."
        ),
        parameters=_NO_ARGS,
        handler=_get_performance_summary,
        scope="workspace",
    ),
    ToolSpec(
        name="find_similar_cases",
        description=(
            "Platform-global market case memory: fingerprint the current stored window "
            "and return past moments that resemble it above the similarity floor, with "
            "how each resolved. Shared market fact — not this workspace's record, and "
            "never combined with it."
        ),
        parameters=_CASE_PARAMS,
        handler=_find_similar_cases,
        scope="platform",
    ),
    ToolSpec(
        name="get_case_outcome_stats",
        description=(
            "Aggregate forward outcomes of the market cases similar to the current "
            "window. Below the minimum sample the rates are withheld and 'sufficient' "
            "is false — counts only, honestly."
        ),
        parameters=_CASE_PARAMS,
        handler=_get_case_outcome_stats,
        scope="platform",
    ),
)

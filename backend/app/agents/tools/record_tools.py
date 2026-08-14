"""Workspace record tools: the tenant's own recommendations, trades, journal.

Workspace-scoped — every handler reads through the RLS-bound session on the
context and none accepts a scope filter. Identity comes from ``context.tenant``
alone: dispatch refuses these tools on an unbound context, and there is no
workspace/tenant/user argument for a caller to widen its own access with.

Every list is bounded (default 20 rows, hard cap 100) so a tool call cannot
dump a whole table into a prompt. Everything here is a read; the services'
write functions are simply never called.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.registry import ToolContext, ToolSpec
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.recommendation import RecommendationReevaluation, RecommendationRevision, Thesis
from app.models.symbol import Symbol
from app.services import (
    alert_service,
    chart_semantic_service,
    journal_service,
    recommendation_service,
    trade_service,
    watchlist_service,
)
from app.services.recommendations import reevaluation, revisions

__all__ = ["TOOLS"]

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _tenant(context: ToolContext) -> TenantContext:
    """Narrow the optional tenant. Dispatch already refused unbound contexts."""
    tenant = context.tenant
    assert tenant is not None
    return tenant


def _limit(arguments: dict[str, Any], default: int = DEFAULT_LIMIT) -> int:
    raw = int(arguments.get("limit", default))
    return max(1, min(raw, MAX_LIMIT))


def _recommendation_id(arguments: dict[str, Any]) -> uuid.UUID:
    raw = arguments.get("recommendation_id")
    if not raw:
        raise ValueError("recommendation_id is required")
    return uuid.UUID(str(raw))


async def _symbol_codes(session: AsyncSession, symbol_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Codes for a set of symbol ids. Symbols are platform-global rows."""
    if not symbol_ids:
        return {}
    result = await session.execute(select(Symbol).where(Symbol.id.in_(symbol_ids)))
    return {row.id: row.code for row in result.scalars().all()}


async def _get_workspace_context(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Identity as data, from the bound context — never from an argument."""
    tenant = _tenant(context)
    return {
        "workspace_id": str(tenant.workspace_id),
        "tenant_id": str(tenant.tenant_id),
        "user_id": str(tenant.user_id),
    }


async def _list_recommendations(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    rows = await recommendation_service.list_recommendations(
        context.session, tenant, limit=_limit(arguments)
    )
    codes = await _symbol_codes(context.session, {row.symbol_id for row in rows})
    return {
        "count": len(rows),
        "recommendations": [
            {
                **recommendation_service.recommendation_to_card(
                    row, symbol_code=codes.get(row.symbol_id)
                ),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


async def _get_recommendation(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    rec_id = _recommendation_id(arguments)
    rec = await recommendation_service.get_recommendation(context.session, tenant, rec_id)
    if rec is None:
        return {"error": "NOT_FOUND", "detail": f"recommendation {rec_id} not found"}
    code = await recommendation_service.resolve_symbol_code(context.session, rec.symbol_id)
    return {
        **recommendation_service.recommendation_to_card(rec, symbol_code=code),
        "created_at": rec.created_at.isoformat(),
    }


def _revision_to_dict(row: RecommendationRevision) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "reason": row.reason,
        "declared_status": row.declared_status,
        "previous_status": row.previous_status,
        "changes": row.changes_json,
        "note": row.note,
        "at": row.created_at.isoformat(),
    }


async def _get_recommendation_revisions(
    context: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    tenant = _tenant(context)
    rec_id = _recommendation_id(arguments)
    rec = await recommendation_service.get_recommendation(context.session, tenant, rec_id)
    if rec is None:
        return {"error": "NOT_FOUND", "detail": f"recommendation {rec_id} not found"}
    rows = await revisions.list_revisions(context.session, tenant, rec_id, limit=_limit(arguments))
    return {
        "recommendation_id": str(rec_id),
        # The distinction the revisions module documents: a revision is what one
        # evaluation *declared* at that moment; the row is the live state. Only
        # live_status describes the plan now.
        "live_status": rec.status.value,
        "distinction": (
            "Revisions are history, oldest first. Each declared_status was true "
            "when that evaluation ran; the current state is live_status above."
        ),
        "count": len(rows),
        "revisions": [_revision_to_dict(row) for row in rows],
    }


def _reevaluation_to_dict(row: RecommendationReevaluation) -> dict[str, Any]:
    return {
        "reason": row.reason,
        "detail": row.detail,
        "source": row.source,
        "outcome": row.outcome,
        "revision_seq": row.revision_seq,
        "raised_at": row.raised_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "decision": row.decision_json,
    }


async def _get_reevaluation_history(
    context: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    tenant = _tenant(context)
    rec_id = _recommendation_id(arguments)
    rec = await recommendation_service.get_recommendation(context.session, tenant, rec_id)
    if rec is None:
        return {"error": "NOT_FOUND", "detail": f"recommendation {rec_id} not found"}
    rows = await reevaluation.list_triggers(
        context.session, tenant, rec_id, limit=_limit(arguments)
    )
    return {
        "recommendation_id": str(rec_id),
        "count": len(rows),
        # The whole ledger, newest first — suppressed triggers included, because
        # "the structure broke, why did nothing happen" needs them.
        "history": [_reevaluation_to_dict(row) for row in rows],
    }


async def _list_trades(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    rows = await trade_service.list_trades(context.session, tenant, limit=_limit(arguments))
    codes = await _symbol_codes(context.session, {row.symbol_id for row in rows})
    return {
        "count": len(rows),
        "trades": [
            {
                **trade_service.trade_to_dict(row, symbol_code=codes.get(row.symbol_id)),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


async def _list_journal_entries(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    rows = await journal_service.list_entries(context.session, tenant, limit=_limit(arguments))
    return {
        "count": len(rows),
        "entries": [journal_service.entry_to_dict(row) for row in rows],
    }


async def _list_alerts(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    rows = await alert_service.list_alerts(context.session, tenant)
    # The service returns everything; the bound is applied here so a workspace
    # with years of rows still fits in a prompt. Newest first already.
    bounded = rows[: _limit(arguments)]
    return {
        "count": len(bounded),
        "alerts": [alert_service.alert_to_dict(row) for row in bounded],
    }


async def _list_watchlists(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    lists = await watchlist_service.list_watchlists(context.session, tenant)
    bounded = lists[: _limit(arguments)]
    # Observed last closes from stored candles — reported when present, never
    # computed or invented when absent.
    quotes = await watchlist_service.latest_quotes_for_workspace(context.session, tenant)
    payload = []
    for wl in bounded:
        items = await watchlist_service.watchlist_items(context.session, wl.id)
        payload.append(watchlist_service.watchlist_to_dict(wl, items, quotes=quotes))
    return {"count": len(payload), "watchlists": payload}


async def _list_chart_annotations(
    context: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    tenant = _tenant(context)
    # This service filters by tenant columns but does not bind the session
    # itself, so bind here — RLS is the scoping that actually holds.
    await bind_workspace_rls(context.session, tenant)
    raw_analysis_id = arguments.get("analysis_id")
    rows = await chart_semantic_service.list_annotations(
        context.session,
        tenant,
        analysis_id=uuid.UUID(str(raw_analysis_id)) if raw_analysis_id else None,
        limit=_limit(arguments),
    )
    return {
        "count": len(rows),
        "annotations": [chart_semantic_service.annotation_to_dict(row) for row in rows],
    }


def _thesis_to_dict(row: Thesis) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "recommendation_id": str(row.recommendation_id),
        "statement": row.statement,
        "status": row.status.value,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "created_at": row.created_at.isoformat(),
    }


async def _list_theses(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(context)
    rows = await recommendation_service.list_theses(
        context.session, tenant, limit=_limit(arguments)
    )
    return {"count": len(rows), "theses": [_thesis_to_dict(row) for row in rows]}


_LIMIT_PARAM = {
    "type": "integer",
    "description": f"Rows to return, 1-{MAX_LIMIT}. Default {DEFAULT_LIMIT}.",
}
_RECOMMENDATION_ID_PARAM = {
    "type": "string",
    "description": "Recommendation id (UUID string).",
}

_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}}


def _list_params() -> dict[str, Any]:
    return {"type": "object", "properties": {"limit": _LIMIT_PARAM}}


def _recommendation_params() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"recommendation_id": _RECOMMENDATION_ID_PARAM},
        "required": ["recommendation_id"],
    }


def _recommendation_list_params() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "recommendation_id": _RECOMMENDATION_ID_PARAM,
            "limit": _LIMIT_PARAM,
        },
        "required": ["recommendation_id"],
    }


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_workspace_context",
        description="The bound workspace, tenant and user ids for this conversation.",
        parameters=_NO_ARGS,
        handler=_get_workspace_context,
        scope="workspace",
    ),
    ToolSpec(
        name="list_recommendations",
        description="Recent recommendations in this workspace as cards, newest first.",
        parameters=_list_params(),
        handler=_list_recommendations,
        scope="workspace",
    ),
    ToolSpec(
        name="get_recommendation",
        description="One recommendation as a card, by id.",
        parameters=_recommendation_params(),
        handler=_get_recommendation,
        scope="workspace",
    ),
    ToolSpec(
        name="get_recommendation_revisions",
        description=(
            "The revision history of one recommendation, oldest first. Revisions "
            "are what past evaluations declared; the live status comes back "
            "separately and is the only one that describes the plan now."
        ),
        parameters=_recommendation_list_params(),
        handler=_get_recommendation_revisions,
        scope="workspace",
    ),
    ToolSpec(
        name="get_reevaluation_history",
        description=(
            "The re-evaluation ledger for one recommendation, newest first — "
            "every trigger raised and what became of it, suppressed ones included."
        ),
        parameters=_recommendation_list_params(),
        handler=_get_reevaluation_history,
        scope="workspace",
    ),
    ToolSpec(
        name="list_trades",
        description="The manual trade log for this workspace, newest first.",
        parameters=_list_params(),
        handler=_list_trades,
        scope="workspace",
    ),
    ToolSpec(
        name="list_journal_entries",
        description="The user's journal entries, newest first.",
        parameters=_list_params(),
        handler=_list_journal_entries,
        scope="workspace",
    ),
    ToolSpec(
        name="list_alerts",
        description="The user's configured alerts, newest first.",
        parameters=_list_params(),
        handler=_list_alerts,
        scope="workspace",
    ),
    ToolSpec(
        name="list_watchlists",
        description=(
            "The workspace's watchlists with their symbols and the last stored "
            "close where one exists."
        ),
        parameters=_list_params(),
        handler=_list_watchlists,
        scope="workspace",
    ),
    ToolSpec(
        name="list_chart_annotations",
        description="Semantic chart annotations in this workspace, most recently updated first.",
        parameters={
            "type": "object",
            "properties": {
                "analysis_id": {
                    "type": "string",
                    "description": "Optional analysis id (UUID) to filter by.",
                },
                "limit": _LIMIT_PARAM,
            },
        },
        handler=_list_chart_annotations,
        scope="workspace",
    ),
    ToolSpec(
        name="list_theses",
        description="Theses in this workspace, newest first.",
        parameters=_list_params(),
        handler=_list_theses,
        scope="workspace",
    ),
)

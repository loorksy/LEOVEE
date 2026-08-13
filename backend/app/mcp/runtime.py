from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.symbols import DEFAULT_SYMBOL
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.mcp import McpAuditEvent, McpSession
from app.services import (
    chart_semantic_service,
    entitlement_service,
    market_data,
    recommendation_service,
)


class McpToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


TOOL_NAMES = frozenset(
    {
        "market.get_candles",
        "chart.get_annotations",
        "recommendation.get",
        "workspace.get_context",
    }
)


async def open_session(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    client_info: dict[str, Any] | None = None,
) -> McpSession:
    await bind_workspace_rls(session, tenant)
    row = McpSession(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
        client_info=client_info or {},
        started_at=utc_now(),
        last_seen_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return row


async def record_audit(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    tool_name: str,
    duration_ms: int,
    session_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> McpAuditEvent:
    event = McpAuditEvent(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
        session_id=session_id,
        tool_name=tool_name,
        duration_ms=duration_ms,
        metadata_json=metadata or {},
    )
    session.add(event)
    await session.flush()
    return event


async def invoke_tool(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    mcp_session_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    if tool_name not in TOOL_NAMES:
        raise McpToolError("NOT_FOUND", f"Unknown tool: {tool_name}")

    await entitlement_service.check_metric_limit(session, tenant, "mcp.call")

    started = time.perf_counter()
    try:
        payload = await _dispatch_tool(session, tenant, tool_name, arguments)
    except McpToolError:
        raise
    except Exception as exc:
        raise McpToolError("INTERNAL", str(exc)) from exc
    duration_ms = int((time.perf_counter() - started) * 1000)
    await record_audit(
        session,
        tenant,
        tool_name=tool_name,
        duration_ms=duration_ms,
        session_id=mcp_session_id,
        metadata={"arguments": arguments},
    )
    await entitlement_service.record_usage(
        session,
        tenant,
        "mcp.call",
        metadata={"tool": tool_name},
    )
    return {"schema_version": 1, "tool": tool_name, "result": payload}


async def _dispatch_tool(
    session: AsyncSession,
    tenant: TenantContext,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "workspace.get_context":
        return {
            "workspace_id": str(tenant.workspace_id),
            "tenant_id": str(tenant.tenant_id),
            "user_id": str(tenant.user_id),
        }
    if tool_name == "market.get_candles":
        symbol = str(arguments.get("symbol", DEFAULT_SYMBOL)).upper()
        from app.models.enums import Timeframe

        tf = Timeframe(str(arguments.get("timeframe", "H1")))
        count = int(arguments.get("count", 50))
        _sym, candles = await market_data.fetch_and_store_candles(
            session,
            symbol_code=symbol,
            timeframe=tf,
            count=min(count, 200),
        )
        return {
            "symbol": symbol,
            "candles": [market_data.candle_to_dict(c) for c in candles],
        }
    if tool_name == "chart.get_annotations":
        rows = await chart_semantic_service.list_annotations(session, tenant, limit=50)
        return {
            "items": [chart_semantic_service.annotation_to_dict(r) for r in rows],
        }
    if tool_name == "recommendation.get":
        rec_id = arguments.get("recommendation_id")
        if not rec_id:
            raise McpToolError("INVALID_ARGUMENT", "recommendation_id required")
        rec = await recommendation_service.get_recommendation(
            session,
            tenant,
            uuid.UUID(str(rec_id)),
        )
        if rec is None:
            raise McpToolError("NOT_FOUND", "Recommendation not found")
        symbol_code = await recommendation_service.resolve_symbol_code(session, rec.symbol_id)
        return recommendation_service.recommendation_to_card(rec, symbol_code=symbol_code)
    raise McpToolError("NOT_FOUND", f"Unhandled tool {tool_name}")

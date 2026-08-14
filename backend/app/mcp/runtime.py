"""The MCP transport over the one tool registry.

This module used to carry its own four hardcoded tools with their own dispatch
— a second tool surface that could drift from the one the agent loop serves.
M11 removes that: the registry in ``app.agents.tools`` is the single source of
truth, and MCP is a *transport* over it. One registry, two doors, one
permission model — a tool cannot behave differently depending on which door it
came through.

What this layer adds, and all it adds:

- **Workspace binding.** The session is RLS-bound to the caller's tenant before
  any dispatch, and the registry's own scope check backs it up: a workspace
  tool on an unbound context is refused, surfaced here as FORBIDDEN.
- **Entitlements, audit, usage.** Every call is entitlement-checked as
  ``mcp.call``, audited with the resolved tool name, and metered.
- **Error translation.** The registry returns errors as data so a model can
  read and correct itself mid-loop; an HTTP client needs status codes instead,
  so error payloads become ``McpToolError`` with a code the route can map.

Legacy dotted names stay working as aliases. One deliberate behaviour change
rides along: ``market.get_candles`` used to fetch from the provider as a side
effect; the unified ``get_candles`` reads stored rows, because a read surface
does not fetch as a side effect.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import TOOLS, ToolContext, dispatch_tool
from app.core.datetime_utils import utc_now
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.mcp import McpAuditEvent, McpSession
from app.services import entitlement_service


class McpToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


#: The dotted names the first MCP cut shipped, resolved to registry tools.
#: Kept indefinitely: renaming a published tool breaks every client quietly.
TOOL_ALIASES: dict[str, str] = {
    "market.get_candles": "get_candles",
    "chart.get_annotations": "list_chart_annotations",
    "recommendation.get": "get_recommendation",
    "workspace.get_context": "get_workspace_context",
}

#: Every name the transport accepts. Derived, never listed by hand — a tool
#: added to the registry is exposed here with no second registration step.
TOOL_NAMES = frozenset(TOOLS) | frozenset(TOOL_ALIASES)

#: How error payloads from the registry translate to transport codes. The
#: registry speaks to a model (errors as data, self-correctable); this layer
#: speaks to HTTP clients (status codes). Anything not named here is INTERNAL:
#: an unrecognised failure must read as a failure, not as a bad argument.
_ERROR_CODES: dict[str, str] = {
    "NOT_FOUND": "NOT_FOUND",
    "unknown_tool": "NOT_FOUND",
    "workspace_context_required": "FORBIDDEN",
    "ValueError": "INVALID_ARGUMENT",
    "UnknownSymbolError": "INVALID_ARGUMENT",
}


def resolve_tool_name(tool_name: str) -> str:
    """Canonical registry name, or NOT_FOUND for a name in neither table."""
    resolved = TOOL_ALIASES.get(tool_name, tool_name)
    if resolved not in TOOLS:
        raise McpToolError("NOT_FOUND", f"Unknown tool: {tool_name}")
    return resolved


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
    resolved = resolve_tool_name(tool_name)

    await entitlement_service.check_metric_limit(session, tenant, "mcp.call")
    # Bound here as well as in open_session: invoke_tool must not depend on the
    # caller having opened a session first to be workspace-safe.
    await bind_workspace_rls(session, tenant)

    started = time.perf_counter()
    payload = await dispatch_tool(
        ToolContext(session=session, tenant=tenant), resolved, arguments or {}
    )
    if isinstance(payload.get("error"), str):
        error = str(payload["error"])
        detail = str(payload.get("detail") or error)
        raise McpToolError(_ERROR_CODES.get(error, "INTERNAL"), detail)
    duration_ms = int((time.perf_counter() - started) * 1000)

    metadata: dict[str, Any] = {"arguments": arguments}
    if resolved != tool_name:
        metadata["alias"] = tool_name
    await record_audit(
        session,
        tenant,
        tool_name=resolved,
        duration_ms=duration_ms,
        session_id=mcp_session_id,
        metadata=metadata,
    )
    await entitlement_service.record_usage(
        session,
        tenant,
        "mcp.call",
        metadata={"tool": resolved},
    )
    # The envelope echoes the name the client asked with — an alias caller gets
    # its own vocabulary back, and the audit trail holds the resolved name.
    return {"schema_version": 1, "tool": tool_name, "result": payload}

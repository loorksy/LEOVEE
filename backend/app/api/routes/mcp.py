from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.mcp import server as mcp_server
from app.mcp.runtime import McpToolError, invoke_tool, open_session
from app.services.entitlement_service import EntitlementError

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class McpInvokeRequest(BaseModel):
    tool: str = Field(min_length=3, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
async def list_mcp_tools() -> dict[str, Any]:
    return {"tools": mcp_server.list_tools()}


@router.get("/apps")
async def list_mcp_apps() -> dict[str, Any]:
    return {"items": mcp_server.list_app_ids()}


@router.get("/apps/{app_id}/manifest")
async def get_mcp_app_manifest(app_id: str) -> JSONResponse:
    try:
        manifest = mcp_server.load_app_manifest(app_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc
    csp = manifest.get("contentSecurityPolicy", "")
    return JSONResponse(
        content=manifest,
        headers={
            "Content-Security-Policy": csp,
            "X-Leovee-MCP-App": app_id,
        },
    )


@router.post("/tools/invoke")
async def invoke_mcp_tool_http(
    body: McpInvokeRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    mcp_session = await open_session(session, tenant, client_info={"transport": "http"})
    try:
        return await invoke_tool(
            session,
            tenant,
            tool_name=body.tool,
            arguments=body.arguments,
            mcp_session_id=mcp_session.id,
        )
    except EntitlementError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except McpToolError as exc:
        status_code = status.HTTP_404_NOT_FOUND
        if exc.code in {"FORBIDDEN", "UNAUTHORIZED"}:
            status_code = status.HTTP_403_FORBIDDEN
        elif exc.code == "INVALID_ARGUMENT":
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=exc.message) from exc

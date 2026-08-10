from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceDetailResponse, WorkspaceListResponse, WorkspaceSummary
from app.services import workspace_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def _to_summary(ws: Workspace) -> WorkspaceSummary:
    return WorkspaceSummary(
        id=ws.id,
        tenant_id=ws.tenant_id,
        name=ws.name,
        slug=ws.slug,
        owner_user_id=ws.owner_user_id,
        status=ws.status.value,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> WorkspaceListResponse:
    items = await workspace_service.list_workspaces_for_user(
        session,
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
    )
    return WorkspaceListResponse(items=[_to_summary(ws) for ws in items])


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> WorkspaceDetailResponse:
    ws = await workspace_service.get_workspace_for_user(
        session,
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
        workspace_id=workspace_id,
    )
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceDetailResponse(
        id=ws.id,
        tenant_id=ws.tenant_id,
        name=ws.name,
        slug=ws.slug,
        owner_user_id=ws.owner_user_id,
        status=ws.status.value,
        settings_json=ws.settings_json,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )

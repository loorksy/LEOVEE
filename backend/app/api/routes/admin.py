from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.conversation import Conversation
from app.models.organization import Organization
from app.models.rbac import Role
from app.models.recommendation import Recommendation
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def require_platform_admin(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> TenantContext:
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == tenant.workspace_id,
            WorkspaceMember.user_id == tenant.user_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a workspace member")
    role = await session.get(Role, member.role_id)
    if role is None or role.code not in {"SUPER_ADMIN", "ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return tenant


@router.get("/overview")
async def admin_overview(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(require_platform_admin)],
) -> dict[str, object]:
    users = await session.scalar(select(func.count()).select_from(User))
    orgs = await session.scalar(select(func.count()).select_from(Organization))
    workspaces = await session.scalar(select(func.count()).select_from(Workspace))
    conversations = await session.scalar(select(func.count()).select_from(Conversation))
    recommendations = await session.scalar(select(func.count()).select_from(Recommendation))
    return {
        "users": int(users or 0),
        "organizations": int(orgs or 0),
        "workspaces": int(workspaces or 0),
        "conversations": int(conversations or 0),
        "recommendations": int(recommendations or 0),
        "workspace_id": str(tenant.workspace_id),
    }

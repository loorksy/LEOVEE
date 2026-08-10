from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.rbac import Role
from app.models.workspace_member import WorkspaceMember

_ADMIN_ROLES = frozenset({"SUPER_ADMIN", "ADMIN"})
_SUPPORT_ROLES = frozenset({"SUPER_ADMIN", "ADMIN", "SUPPORT"})


async def _workspace_role_code(
    session: AsyncSession,
    tenant: TenantContext,
) -> str:
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == tenant.workspace_id,
            WorkspaceMember.user_id == tenant.user_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a workspace member")
    role = await session.get(Role, member.role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not found")
    return role.code


async def require_platform_admin(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> TenantContext:
    code = await _workspace_role_code(session, tenant)
    if code not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return tenant


async def require_support_audit(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> TenantContext:
    code = await _workspace_role_code(session, tenant)
    if code not in _SUPPORT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audit access required")
    return tenant

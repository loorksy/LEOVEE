import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import OrganizationMemberRole
from app.models.organization_member import OrganizationMember
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Resolved tenant scope for the current authenticated user."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    organization_member_id: uuid.UUID
    role: OrganizationMemberRole
    workspace_id: uuid.UUID
    workspace_member_id: uuid.UUID


class TenantResolutionError(Exception):
    """User has no tenant membership or client tenant hint is invalid."""


class WorkspaceResolutionError(Exception):
    """User cannot access the requested workspace."""


async def resolve_tenant_context(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    client_tenant_id: uuid.UUID | None = None,
) -> TenantContext:
    """
    Derive tenant_id from membership. Never trust client_tenant_id without verification.
    Workspace is resolved separately via resolve_workspace_context.
    """
    result = await session.execute(
        select(OrganizationMember).where(OrganizationMember.user_id == user_id)
    )
    memberships = list(result.scalars().all())
    if not memberships:
        raise TenantResolutionError("User is not a member of any organization")

    if client_tenant_id is not None:
        for membership in memberships:
            if membership.tenant_id == client_tenant_id:
                return await _tenant_with_default_workspace(session, membership, user_id)
        raise TenantResolutionError("User is not a member of the requested organization")

    membership = _pick_primary_membership(memberships)
    return await _tenant_with_default_workspace(session, membership, user_id)


async def resolve_workspace_context(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    client_workspace_id: uuid.UUID | None = None,
) -> TenantContext:
    if client_workspace_id is None:
        return tenant

    if client_workspace_id == tenant.workspace_id:
        return tenant

    membership = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == client_workspace_id,
            WorkspaceMember.user_id == tenant.user_id,
            WorkspaceMember.tenant_id == tenant.tenant_id,
        )
    )
    if membership is None:
        raise WorkspaceResolutionError("User is not a member of the requested workspace")

    return TenantContext(
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
        organization_member_id=tenant.organization_member_id,
        role=tenant.role,
        workspace_id=membership.workspace_id,
        workspace_member_id=membership.id,
    )


async def _tenant_with_default_workspace(
    session: AsyncSession,
    membership: OrganizationMember,
    user_id: uuid.UUID,
) -> TenantContext:
    ws_member = await session.scalar(
        select(WorkspaceMember)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.tenant_id == membership.tenant_id,
        )
        .order_by(Workspace.created_at.asc())
        .limit(1)
    )
    if ws_member is None:
        raise TenantResolutionError("User has no workspace in this organization")

    return TenantContext(
        tenant_id=membership.tenant_id,
        user_id=user_id,
        organization_member_id=membership.id,
        role=membership.role,
        workspace_id=ws_member.workspace_id,
        workspace_member_id=ws_member.id,
    )


def _pick_primary_membership(memberships: list[OrganizationMember]) -> OrganizationMember:
    role_order = {
        OrganizationMemberRole.ORG_OWNER: 0,
        OrganizationMemberRole.ORG_ADMIN: 1,
        OrganizationMemberRole.ORG_MEMBER: 2,
    }
    return sorted(memberships, key=lambda m: role_order[m.role])[0]


def tenant_resolution_to_http(exc: TenantResolutionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=str(exc),
    )


def workspace_resolution_to_http(exc: WorkspaceResolutionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=str(exc),
    )

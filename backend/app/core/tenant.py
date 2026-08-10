import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import OrganizationMemberRole
from app.models.organization_member import OrganizationMember


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Resolved tenant scope for the current authenticated user."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    organization_member_id: uuid.UUID
    role: OrganizationMemberRole


class TenantResolutionError(Exception):
    """User has no tenant membership or client tenant hint is invalid."""


async def resolve_tenant_context(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    client_tenant_id: uuid.UUID | None = None,
) -> TenantContext:
    """
    Derive tenant_id from membership. Never trust client_tenant_id without verification.
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
                return TenantContext(
                    tenant_id=membership.tenant_id,
                    user_id=user_id,
                    organization_member_id=membership.id,
                    role=membership.role,
                )
        raise TenantResolutionError("User is not a member of the requested organization")

    membership = _pick_primary_membership(memberships)
    return TenantContext(
        tenant_id=membership.tenant_id,
        user_id=user_id,
        organization_member_id=membership.id,
        role=membership.role,
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

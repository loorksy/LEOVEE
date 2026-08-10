import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantResolutionError, resolve_tenant_context
from app.models import Organization, OrganizationMember, User
from app.models.base import OrganizationMemberRole, OrganizationStatus, UserStatus
from app.services.workspace_service import create_default_workspace
from app.tests.conftest import seed_user_org


async def test_resolve_tenant_picks_primary_membership(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session)

    ctx = await resolve_tenant_context(db_session, user.id)

    assert ctx.tenant_id == org.id
    assert ctx.user_id == user.id
    assert ctx.role == OrganizationMemberRole.ORG_OWNER


async def test_resolve_tenant_honors_verified_client_tenant_id(db_session: AsyncSession) -> None:
    user, org_a, _ = await seed_user_org(db_session, email="multi@leovee.test", slug="org-a")
    org_b = Organization(name="Other", slug="org-b", status=OrganizationStatus.ACTIVE)
    db_session.add(org_b)
    await db_session.flush()
    db_session.add(
        OrganizationMember(
            tenant_id=org_b.id,
            user_id=user.id,
            role=OrganizationMemberRole.ORG_MEMBER,
        )
    )
    await db_session.flush()
    await create_default_workspace(
        db_session,
        tenant_id=org_b.id,
        owner_user_id=user.id,
        name="Org B Workspace",
    )
    await db_session.commit()

    ctx = await resolve_tenant_context(db_session, user.id, client_tenant_id=org_b.id)
    assert ctx.tenant_id == org_b.id


async def test_resolve_tenant_rejects_untrusted_client_tenant_id(db_session: AsyncSession) -> None:
    user, _, _ = await seed_user_org(db_session)
    attacker_tenant = uuid.uuid4()

    with pytest.raises(TenantResolutionError):
        await resolve_tenant_context(db_session, user.id, client_tenant_id=attacker_tenant)


async def test_resolve_tenant_user_without_membership(db_session: AsyncSession) -> None:
    orphan = User(email="orphan@leovee.test", status=UserStatus.ACTIVE)
    db_session.add(orphan)
    await db_session.commit()

    with pytest.raises(TenantResolutionError):
        await resolve_tenant_context(db_session, orphan.id)

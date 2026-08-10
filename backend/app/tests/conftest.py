from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Organization, OrganizationMember, User
from app.models.base import OrganizationMemberRole, OrganizationStatus, UserStatus
from app.services.workspace_service import create_default_workspace


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def seed_user_org(
    session: AsyncSession,
    *,
    email: str = "user@leovee.test",
    slug: str = "acme",
) -> tuple[User, Organization, OrganizationMember]:
    org = Organization(name="Acme", slug=slug, status=OrganizationStatus.ACTIVE)
    user = User(email=email, status=UserStatus.ACTIVE)
    session.add_all([org, user])
    await session.flush()
    membership = OrganizationMember(
        tenant_id=org.id,
        user_id=user.id,
        role=OrganizationMemberRole.ORG_OWNER,
    )
    session.add(membership)
    await session.flush()
    await create_default_workspace(
        session,
        tenant_id=org.id,
        owner_user_id=user.id,
        name="Default Workspace",
    )
    await session.commit()
    return user, org, membership

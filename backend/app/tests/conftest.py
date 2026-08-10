from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncGenerator, Generator
from functools import lru_cache

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Organization, OrganizationMember, User
from app.models.base import OrganizationMemberRole, OrganizationStatus, UserStatus
from app.services.workspace_service import create_default_workspace


def _to_asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@lru_cache(maxsize=1)
def _postgres_container_url() -> str:
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()
    return _to_asyncpg_url(container.get_connection_url())


@pytest.fixture(scope="session")
def postgres_database_url() -> Generator[str, None, None]:
    env_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if env_url:
        yield _to_asyncpg_url(env_url)
        return
    yield _postgres_container_url()


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_database_url: str) -> Generator[str, None, None]:
    sync_url = postgres_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    env = {**os.environ, "DATABASE_URL": postgres_database_url}
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    yield postgres_database_url
    _ = sync_url


@pytest.fixture
async def db_session(migrated_postgres_url: str) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(migrated_postgres_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(table.delete())
        yield session
    await engine.dispose()


async def seed_user_org(
    session: AsyncSession,
    *,
    email: str = "user@example.com",
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
    await session.flush()
    return user, org, membership

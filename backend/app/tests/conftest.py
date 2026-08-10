from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator, Generator
from functools import lru_cache

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database import app_database_url_from_migration_url
from app.models import Organization, OrganizationMember, User
from app.models.base import OrganizationMemberRole, OrganizationStatus, UserStatus
from app.services.workspace_service import create_default_workspace


@pytest.fixture(autouse=True)
def _configure_app_database(
    monkeypatch: pytest.MonkeyPatch,
    migrated_postgres: str,
) -> Generator[None, None, None]:
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", migrated_postgres)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
def postgres_migration_url() -> Generator[str, None, None]:
    env_url = (
        os.environ.get("TEST_DATABASE_MIGRATION_URL")
        or os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_MIGRATION_URL")
        or os.environ.get("DATABASE_URL")
    )
    if env_url:
        yield _to_asyncpg_url(env_url)
        return
    yield _postgres_container_url()


@pytest.fixture(scope="session")
def postgres_app_url(postgres_migration_url: str) -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit and "leovee_app" in explicit:
        return _to_asyncpg_url(explicit)
    return app_database_url_from_migration_url(postgres_migration_url)


@pytest.fixture(scope="session")
def migrated_postgres(
    postgres_migration_url: str, postgres_app_url: str
) -> Generator[str, None, None]:
    async def _reset_schema() -> None:
        engine = create_async_engine(postgres_migration_url, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await engine.dispose()

    asyncio.run(_reset_schema())

    env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
    env["DATABASE_MIGRATION_URL"] = postgres_migration_url
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    yield postgres_app_url


@pytest.fixture(scope="session")
def migrated_postgres_url(migrated_postgres: str) -> str:
    return migrated_postgres


async def _truncate_public_schema(engine_url: str) -> None:
    engine = create_async_engine(engine_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DO $$ DECLARE r RECORD;
                BEGIN
                  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
                  END LOOP;
                END $$;
                """
            )
        )
    await engine.dispose()


@pytest.fixture
async def db_session(
    migrated_postgres: str,
    postgres_migration_url: str,
) -> AsyncGenerator[AsyncSession, None]:
    await _truncate_public_schema(postgres_migration_url)
    engine = create_async_engine(migrated_postgres, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def privileged_session(
    postgres_migration_url: str,
) -> AsyncGenerator[AsyncSession, None]:
    """Migration/superuser session — not used by API handlers."""
    engine = create_async_engine(postgres_migration_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
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

from collections.abc import AsyncGenerator
from functools import lru_cache
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.infrastructure.rls import clear_rls_session_context

APP_DB_ROLE = "leovee_app"


@lru_cache
def get_migration_engine() -> AsyncEngine | None:
    """Privileged connection for migrations only — never use in request handlers."""
    settings = get_settings()
    url = settings.database_migration_url or settings.database_url
    if not url:
        return None
    return create_async_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> AsyncEngine | None:
    """Runtime application engine (must connect as leovee_app)."""
    settings = get_settings()
    if not settings.database_url:
        return None
    _assert_app_database_url(settings.database_url)
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )


def _assert_app_database_url(url: str) -> None:
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    username = parsed.username or ""
    if username and username != APP_DB_ROLE:
        msg = (
            f"DATABASE_URL must authenticate as '{APP_DB_ROLE}' for RLS enforcement; "
            f"got user '{username}'. Use DATABASE_MIGRATION_URL for privileged migrations."
        )
        raise RuntimeError(msg)


def app_database_url_from_migration_url(migration_url: str) -> str:
    """Derive leovee_app runtime URL from a postgres superuser test URL."""
    normalized = migration_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if not normalized.startswith("postgresql+asyncpg://"):
        normalized = normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
    parsed = urlparse(normalized)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    db = parsed.path or "/leovee_test"
    return f"postgresql+asyncpg://{APP_DB_ROLE}:leovee_app@{host}{port}{db}"


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    engine = get_engine()
    if engine is None:
        return None
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with factory() as session:
        await clear_rls_session_context(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def verify_runtime_db_role(session: AsyncSession) -> None:
    """Assert the session is not a superuser / BYPASSRLS role."""
    row = await session.execute(
        text(
            """
            SELECT rolname, rolsuper, rolbypassrls
            FROM pg_roles
            WHERE rolname = current_user
            """
        )
    )
    rolname, rolsuper, rolbypassrls = row.one()
    if rolname != APP_DB_ROLE or rolsuper or rolbypassrls:
        raise RuntimeError(
            f"Runtime DB role must be {APP_DB_ROLE} without superuser/BYPASSRLS; "
            f"got {rolname} rolsuper={rolsuper} rolbypassrls={rolbypassrls}"
        )

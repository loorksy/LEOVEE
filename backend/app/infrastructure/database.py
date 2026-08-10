from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine | None:
    settings = get_settings()
    if not settings.database_url:
        return None
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )


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
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

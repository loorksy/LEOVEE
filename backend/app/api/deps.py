import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.tenant import (
    TenantContext,
    TenantResolutionError,
    resolve_tenant_context,
    tenant_resolution_to_http,
)
from app.infrastructure.database import get_db_session


async def get_current_user_id(
    settings: Annotated[Settings, Depends(get_settings)],
    x_leovee_user_id: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """
    Temporary user resolution until Phase 4 JWT auth.

    In development/test, pass X-Leovee-User-Id header (internal only).
    """
    if settings.environment in {"development", "test"} and x_leovee_user_id:
        try:
            return uuid.UUID(x_leovee_user_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Leovee-User-Id",
            ) from exc
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_tenant_context(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> TenantContext:
    client_tenant_id: uuid.UUID | None = None
    if x_tenant_id:
        try:
            client_tenant_id = uuid.UUID(x_tenant_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Tenant-Id",
            ) from exc

    try:
        return await resolve_tenant_context(
            session,
            user_id,
            client_tenant_id=client_tenant_id,
        )
    except TenantResolutionError as exc:
        raise tenant_resolution_to_http(exc) from exc

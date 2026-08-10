import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.tenant import (
    TenantContext,
    TenantResolutionError,
    WorkspaceResolutionError,
    resolve_tenant_context,
    resolve_workspace_context,
    tenant_resolution_to_http,
    workspace_resolution_to_http,
)
from app.infrastructure.database import get_db_session
from app.infrastructure.rls import set_rls_session_context
from app.services.auth_service import AuthError, get_user_for_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_leovee_user_id: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        try:
            user, _ = await get_user_for_access_token(session, settings, credentials.credentials)
            return user.id
        except AuthError as exc:
            status_code = status.HTTP_401_UNAUTHORIZED
            if exc.code == "email_not_verified":
                status_code = status.HTTP_403_FORBIDDEN
            raise HTTPException(
                status_code=status_code,
                detail={"message": str(exc), "code": exc.code},
            ) from exc

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


async def get_workspace_context(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    x_workspace_id: Annotated[str | None, Header()] = None,
) -> TenantContext:
    client_workspace_id: uuid.UUID | None = None
    if x_workspace_id:
        try:
            client_workspace_id = uuid.UUID(x_workspace_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Workspace-Id",
            ) from exc

    try:
        ctx = await resolve_workspace_context(
            session,
            tenant,
            client_workspace_id=client_workspace_id,
        )
    except WorkspaceResolutionError as exc:
        raise workspace_resolution_to_http(exc) from exc

    await set_rls_session_context(
        session,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user_id,
    )
    return ctx

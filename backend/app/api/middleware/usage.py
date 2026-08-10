from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.tenant import resolve_tenant_context, resolve_workspace_context
from app.infrastructure.database import get_session_factory
from app.services.auth_service import AuthError, get_user_for_access_token
from app.services.entitlement_service import EntitlementError, check_metric_limit

USAGE_PATHS: dict[str, str] = {
    "/api/v1/analysis": "analysis.run",
}


class UsageLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "POST":
            return await call_next(request)

        metric: str | None = None
        for prefix, name in USAGE_PATHS.items():
            if request.url.path.startswith(prefix):
                metric = name
                break
        if metric is None:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return await call_next(request)

        token = auth_header.split(" ", 1)[1].strip()
        factory = get_session_factory()
        if factory is None:
            return await call_next(request)

        settings = get_settings()
        try:
            async with factory() as session:
                try:
                    await get_user_for_access_token(session, settings, token)
                except AuthError:
                    return await call_next(request)

                from app.core.security import decode_access_token

                claims = decode_access_token(settings, token)
                user_id = __import__("uuid").UUID(claims["sub"])
                client_tenant = request.headers.get("X-Tenant-Id")
                client_workspace = request.headers.get("X-Workspace-Id")
                tenant_uuid = __import__("uuid").UUID(client_tenant) if client_tenant else None
                workspace_uuid = (
                    __import__("uuid").UUID(client_workspace) if client_workspace else None
                )
                tenant = await resolve_tenant_context(
                    session,
                    user_id,
                    client_tenant_id=tenant_uuid,
                )
                workspace = await resolve_workspace_context(
                    session,
                    tenant,
                    client_workspace_id=workspace_uuid,
                )
                await check_metric_limit(session, workspace, metric)
                await session.commit()
        except EntitlementError as exc:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        except Exception:
            return await call_next(request)

        return await call_next(request)

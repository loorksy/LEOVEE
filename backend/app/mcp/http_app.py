"""Standalone FastAPI app for the leovee-mcp compose service (Batch 5)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import health, mcp
from app.core.logging import configure_logging
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.entitlement_service import EntitlementError


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


def create_mcp_app() -> FastAPI:
    """MCP-only surface: health + MCP tools/apps (same auth/RLS as API)."""
    application = FastAPI(title="Leovee MCP", version="0.1.0", lifespan=lifespan)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(ObservabilityMiddleware)

    @application.exception_handler(EntitlementError)
    async def entitlement_error_handler(
        _request: Request, exc: EntitlementError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc), "code": getattr(exc, "code", "entitlement")},
        )

    application.include_router(health.router)
    application.include_router(mcp.router)
    return application


app = create_mcp_app()

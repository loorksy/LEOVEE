from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import websocket as ws_router
from app.api.routes import (
    admin,
    alerts,
    analysis,
    api_keys,
    auth,
    billing,
    chart,
    chat,
    health,
    journal,
    markets,
    mcp,
    memory,
    metrics,
    news,
    performance,
    providers,
    recommendations,
    replay,
    tenant,
    theses,
    trades,
    watchlists,
    workspaces,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.observability.sentry_bridge import init_sentry
from app.services.entitlement_service import EntitlementError


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    init_sentry(settings)
    from app.core.startup import validate_production_startup

    validate_production_startup(settings)
    if settings.database_url:
        from app.infrastructure.database import get_session_factory
        from app.infrastructure.seed import ensure_platform_seed

        factory = get_session_factory()
        if factory is not None:
            async with factory() as session:
                await ensure_platform_seed(session)
                await session.commit()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Leovee API",
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(ObservabilityMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(EntitlementError)
    async def _entitlement_error_handler(
        _request: Request,
        exc: EntitlementError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc), "code": exc.code},
        )

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(admin.router)
    application.include_router(billing.router)
    application.include_router(api_keys.router)
    application.include_router(tenant.router)
    application.include_router(workspaces.router)
    application.include_router(markets.router)
    application.include_router(metrics.router)
    application.include_router(performance.router)
    application.include_router(mcp.router)
    application.include_router(news.router)
    application.include_router(providers.router)
    application.include_router(analysis.router)
    application.include_router(chart.router)
    application.include_router(replay.router)
    application.include_router(watchlists.router)
    application.include_router(alerts.router)
    application.include_router(journal.router)
    application.include_router(memory.router)
    application.include_router(recommendations.router)
    application.include_router(trades.router)
    application.include_router(theses.router)
    application.include_router(chat.router)
    application.include_router(ws_router.router)
    return application


app = create_app()

"""Provider configuration status — never returns secret values."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_workspace_context
from app.core.config import get_settings
from app.core.tenant import TenantContext

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get("/status")
async def provider_status(
    _tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    settings = get_settings()
    oanda_env = settings.oanda_environment
    return {
        "finnhub": {
            "configured": bool(settings.finnhub_api_key),
            "status": "ok" if settings.finnhub_api_key else "not_configured",
        },
        "oanda": {
            "configured": bool(settings.oanda_api_token and settings.oanda_account_id),
            "environment": oanda_env,
            "status": "ok"
            if settings.oanda_api_token and settings.oanda_account_id and oanda_env == "practice"
            else "not_configured",
        },
        "anthropic": {
            "configured": bool(settings.anthropic_api_key),
            "status": "ok" if settings.anthropic_api_key else "not_configured",
        },
        "openai": {
            "configured": bool(settings.openai_api_key),
            "status": "ok" if settings.openai_api_key else "not_configured",
        },
        "openrouter": {
            "configured": bool(settings.openrouter_api_key),
            "status": "ok" if settings.openrouter_api_key else "not_configured",
            "mode": "free_rotation" if settings.openrouter_api_key else None,
        },
    }

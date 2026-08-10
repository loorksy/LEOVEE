from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ProviderConfigurationError


def validate_production_startup(settings: Settings) -> None:
    if settings.environment != "production":
        return

    missing: list[str] = []
    if not settings.database_url:
        missing.append("DATABASE_URL")
    if not settings.redis_url:
        missing.append("REDIS_URL")
    if not settings.secret_key or settings.secret_key == "change-me-in-production":
        missing.append("SECRET_KEY")
    if not settings.oanda_api_token:
        missing.append("OANDA_API_TOKEN")
    if not settings.openai_api_key and not settings.anthropic_api_key:
        missing.append("OPENAI_API_KEY or ANTHROPIC_API_KEY")

    if missing:
        raise ProviderConfigurationError(
            "Production startup refused: missing required configuration: " + ", ".join(missing)
        )

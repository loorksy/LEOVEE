from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import Settings
from app.core.errors import ProviderConfigurationError

#: HS256 signs with a key shorter than the hash it feeds; RFC 7518 §3.2 sets 256
#: bits (32 bytes) as the floor, and PyJWT only *warns* below it. The guard turns
#: that warning into a boot refusal.
MIN_SECRET_KEY_BYTES = 32


def _is_local_origin(origin: str) -> bool:
    host = urlparse(origin).hostname or origin
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _database_role(url: str) -> str:
    return urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1)).username or ""


def validate_production_startup(settings: Settings) -> None:
    # OANDA_EXECUTION is refused in *every* environment: it is out of scope
    # (ADR 0005), and no environment is the right one to place a live order in.
    if settings.oanda_execution:
        raise ProviderConfigurationError(
            "OANDA_EXECUTION must be off — order execution is out of scope (ADR 0005)."
        )

    if settings.environment != "production":
        return

    missing: list[str] = []
    if settings.dev_auth_bypass:
        # The impersonation header must never be shippable to production, even
        # by accident. Refuse to boot rather than run with it armed.
        missing.append("DEV_AUTH_BYPASS must be off in production")
    if not settings.trust_proxy_headers:
        # Production sits behind the nginx/Caddy edge, so request.client.host is
        # the proxy. Without this, every client keys to one rate-limit bucket —
        # one abuser locks all tenants out of login/signup/reset.
        missing.append(
            "TRUST_PROXY_HEADERS must be true in production (the API runs behind the edge)"
        )
    if not settings.database_url:
        missing.append("DATABASE_URL")
    elif _database_role(settings.database_url) != "leovee_app":
        # Parse the role rather than substring-match: a db or password containing
        # "leovee_app" must not satisfy the check while the login role is privileged.
        missing.append("DATABASE_URL must authenticate as the leovee_app role")
    if not settings.redis_url:
        missing.append("REDIS_URL")
    if not settings.secret_key or settings.secret_key == "change-me-in-production":
        missing.append("SECRET_KEY")
    elif len(settings.secret_key.encode("utf-8")) < MIN_SECRET_KEY_BYTES:
        missing.append(f"SECRET_KEY must be at least {MIN_SECRET_KEY_BYTES} bytes for HS256")
    if not settings.oanda_api_token:
        missing.append("OANDA_API_TOKEN")
    if (
        not settings.openai_api_key
        and not settings.anthropic_api_key
        and not settings.openrouter_api_key
    ):
        missing.append("OPENAI_API_KEY or ANTHROPIC_API_KEY or OPENROUTER_API_KEY")

    origins = settings.cors_origin_list
    if "*" in origins:
        # Credentialed CORS with a wildcard origin reflects any site's Origin and
        # returns Allow-Credentials: true — a cross-origin credential leak.
        missing.append("CORS_ORIGINS must not be '*' in production (credentials are allowed)")
    elif not origins or all(_is_local_origin(o) for o in origins):
        missing.append("CORS_ORIGINS must name the real production origin(s), not localhost")

    if missing:
        raise ProviderConfigurationError(
            "Production startup refused: missing required configuration: " + ", ".join(missing)
        )

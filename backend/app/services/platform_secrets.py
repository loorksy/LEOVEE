"""Admin-managed platform secrets with encrypted DB storage + runtime overlay.

Secrets set via the admin panel are stored encrypted in `platform_secrets` and
applied on top of env-based Settings so API/worker pick them up without a rebuild.
Never return plaintext secret values to clients — only configured/masked status.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.datetime_utils import utc_now
from app.models.platform_secret import PlatformSecret

# Public env-style keys admins may set. Values never echoed back.
MANAGED_SECRET_KEYS: tuple[str, ...] = (
    "OANDA_API_TOKEN",
    "OANDA_ACCOUNT_ID",
    "OANDA_ENVIRONMENT",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FINNHUB_API_KEY",
    "RESEND_API_KEY",
    "SECRET_KEY",
    "METRICS_BEARER_TOKEN",
    "SENTRY_DSN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
)

# Map env key → Settings field name
_ENV_TO_FIELD: dict[str, str] = {
    "OANDA_API_TOKEN": "oanda_api_token",
    "OANDA_ACCOUNT_ID": "oanda_account_id",
    "OANDA_ENVIRONMENT": "oanda_environment",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
    "TELEGRAM_WEBHOOK_SECRET": "telegram_webhook_secret",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENROUTER_API_KEY": "openrouter_api_key",
    "FINNHUB_API_KEY": "finnhub_api_key",
    "RESEND_API_KEY": "resend_api_key",
    "SECRET_KEY": "secret_key",
    "METRICS_BEARER_TOKEN": "metrics_bearer_token",
    "SENTRY_DSN": "sentry_dsn",
}

_runtime_overrides: dict[str, str] = {}
# Fernet parent key pinned from boot env SECRET_KEY so rotating SECRET_KEY via
# admin does not brick decryption of other rows until re-encrypt runs.
_fernet: Fernet | None = None


class PlatformSecretError(ValueError):
    pass


@dataclass(frozen=True)
class SecretStatus:
    key: str
    configured: bool
    updated_at: datetime | None


def _boot_secret_key() -> str:
    # Read env Settings without applying runtime overrides (avoid recursion).
    return Settings().secret_key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        digest = hashlib.sha256(_boot_secret_key().encode("utf-8")).digest()
        _fernet = Fernet(base64.urlsafe_b64encode(digest))
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise PlatformSecretError("Unable to decrypt platform secret") from exc


def apply_runtime_overrides(base: Settings) -> Settings:
    if not _runtime_overrides:
        return base
    update = {
        _ENV_TO_FIELD[key]: value
        for key, value in _runtime_overrides.items()
        if key in _ENV_TO_FIELD
    }
    if not update:
        return base
    return base.model_copy(update=update)


def get_runtime_overrides() -> dict[str, str]:
    return dict(_runtime_overrides)


def set_runtime_overrides(values: dict[str, str]) -> None:
    """Replace in-memory overlay and clear Settings cache."""
    _runtime_overrides.clear()
    _runtime_overrides.update(values)
    get_settings.cache_clear()


def validate_secret_update(key: str, value: str) -> str:
    if key not in MANAGED_SECRET_KEYS:
        raise PlatformSecretError(f"Unsupported secret key: {key}")
    cleaned = value.strip()
    if key == "OANDA_ENVIRONMENT":
        lowered = cleaned.lower()
        if lowered != "practice":
            raise PlatformSecretError(
                "Only practice OANDA is allowed. Live/funded accounts are forbidden."
            )
        return "practice"
    if key == "OANDA_API_TOKEN" and not cleaned:
        raise PlatformSecretError("OANDA_API_TOKEN cannot be empty when set")
    return cleaned


async def load_runtime_overrides(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(PlatformSecret))
    rows = list(result.scalars().all())
    loaded: dict[str, str] = {}
    for row in rows:
        if row.key not in _ENV_TO_FIELD:
            continue
        try:
            loaded[row.key] = decrypt_secret(row.ciphertext)
        except PlatformSecretError:
            continue
    set_runtime_overrides(loaded)
    return loaded


async def list_secret_status(session: AsyncSession) -> list[SecretStatus]:
    result = await session.execute(select(PlatformSecret))
    by_key = {row.key: row for row in result.scalars().all()}
    # Also treat env-configured keys as configured for UI honesty.
    env = Settings()
    env_configured = {
        key: bool(getattr(env, field, None) or _runtime_overrides.get(key))
        for key, field in _ENV_TO_FIELD.items()
    }
    items: list[SecretStatus] = []
    for key in MANAGED_SECRET_KEYS:
        row = by_key.get(key)
        configured = bool(row) or env_configured.get(key, False)
        items.append(
            SecretStatus(
                key=key,
                configured=configured,
                updated_at=row.updated_at if row else None,
            )
        )
    return items


async def upsert_secrets(
    session: AsyncSession,
    *,
    updates: dict[str, str | None],
    actor_user_id: uuid.UUID | None,
) -> list[SecretStatus]:
    """Upsert or clear secrets. None/missing = keep; empty string = clear."""
    if not updates:
        return await list_secret_status(session)

    for key, raw in updates.items():
        if raw is None:
            continue
        if raw == "":
            existing = await session.get(PlatformSecret, key)
            if existing is not None:
                await session.delete(existing)
            _runtime_overrides.pop(key, None)
            continue
        value = validate_secret_update(key, raw)
        row = await session.get(PlatformSecret, key)
        if row is None:
            row = PlatformSecret(
                key=key,
                ciphertext=encrypt_secret(value),
                updated_by_user_id=actor_user_id,
                updated_at=utc_now(),
            )
            session.add(row)
        else:
            row.ciphertext = encrypt_secret(value)
            row.updated_by_user_id = actor_user_id
            row.updated_at = utc_now()
        _runtime_overrides[key] = value

    await session.flush()
    get_settings.cache_clear()
    return await list_secret_status(session)


def status_payload(items: list[SecretStatus]) -> dict[str, Any]:
    settings = get_settings()
    return {
        "items": [
            {
                "key": item.key,
                "configured": item.configured,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in items
        ],
        "oanda_environment": settings.oanda_environment,
        "oanda_execution_enabled": False,
        "managed_keys": list(MANAGED_SECRET_KEYS),
    }

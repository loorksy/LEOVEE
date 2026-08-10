from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.security import generate_opaque_token, hash_token
from app.core.tenant import TenantContext
from app.models.api_key import ApiKey

API_KEY_PREFIX = "lvk_"
DEFAULT_SCOPES = frozenset({"workspace.read", "markets.read"})


class ApiKeyError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def assert_scopes(granted: list[str], required: str) -> None:
    if required not in granted:
        raise ApiKeyError("scope_denied", f"API key missing scope: {required}")


async def create_api_key(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    name: str,
    scopes: list[str] | None = None,
) -> tuple[ApiKey, str]:
    plain = f"{API_KEY_PREFIX}{generate_opaque_token()}"
    prefix = plain[:12]
    row = ApiKey(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
        name=name,
        key_prefix=prefix,
        key_hash=hash_token(plain),
        scopes=sorted(scopes or DEFAULT_SCOPES),
    )
    session.add(row)
    await session.flush()
    return row, plain


async def list_api_keys(
    session: AsyncSession,
    tenant: TenantContext,
) -> list[ApiKey]:
    result = await session.execute(
        select(ApiKey)
        .where(
            ApiKey.tenant_id == tenant.tenant_id,
            ApiKey.workspace_id == tenant.workspace_id,
            ApiKey.revoked_at.is_(None),
        )
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(
    session: AsyncSession,
    tenant: TenantContext,
    key_id: uuid.UUID,
) -> bool:
    row = await session.get(ApiKey, key_id)
    if row is None or row.workspace_id != tenant.workspace_id:
        return False
    row.revoked_at = utc_now()
    await session.flush()
    return True


async def authenticate_api_key(
    session: AsyncSession,
    *,
    raw_key: str,
    required_scope: str | None = None,
) -> ApiKey:
    if not raw_key.startswith(API_KEY_PREFIX):
        raise ApiKeyError("invalid_key", "Malformed API key")
    digest = hash_token(raw_key)
    row = await session.scalar(select(ApiKey).where(ApiKey.key_hash == digest))
    if row is None or row.revoked_at is not None:
        raise ApiKeyError("invalid_key", "API key not found")
    if row.expires_at is not None and row.expires_at < datetime.now(UTC):
        raise ApiKeyError("expired", "API key expired")
    if required_scope is not None:
        assert_scopes(row.scopes, required_scope)
    row.last_used_at = utc_now()
    await session.flush()
    return row

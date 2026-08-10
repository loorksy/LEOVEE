from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_DENY_ALL_UUID = "00000000-0000-0000-0000-000000000000"


async def clear_rls_session_context(session: AsyncSession) -> None:
    """Deny workspace-scoped access until a workspace context is bound."""
    await session.execute(
        text("SELECT set_config('app.tenant_id', :value, true)"),
        {"value": _DENY_ALL_UUID},
    )
    await session.execute(
        text("SELECT set_config('app.workspace_id', :value, true)"),
        {"value": _DENY_ALL_UUID},
    )
    await session.execute(
        text("SELECT set_config('app.user_id', :value, true)"),
        {"value": _DENY_ALL_UUID},
    )


async def set_rls_session_context(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> None:
    """Set PostgreSQL session variables consumed by RLS policies."""
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    await session.execute(
        text("SELECT set_config('app.workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace_id)},
    )
    if user_id is not None:
        await session.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(user_id)},
        )

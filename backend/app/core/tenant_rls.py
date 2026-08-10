from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.infrastructure.rls import set_rls_session_context


async def bind_workspace_rls(session: AsyncSession, tenant: TenantContext) -> None:
    """Apply PostgreSQL session variables required for workspace RLS policies."""
    await set_rls_session_context(
        session,
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
    )

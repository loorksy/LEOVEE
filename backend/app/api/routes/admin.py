from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_deps import describe_admin_access, require_platform_admin, require_support_audit
from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.infrastructure.database import get_db_session
from app.models.conversation import Conversation
from app.models.learning import AgentRun
from app.models.organization import Organization
from app.models.recommendation import Recommendation
from app.models.user import User
from app.models.workspace import Workspace
from app.services.platform_secrets import (
    PlatformSecretError,
    list_secret_status,
    status_payload,
    upsert_secrets,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AdminSecretsUpdateRequest(BaseModel):
    """Only include keys to change. Empty string clears a secret; omit to keep."""

    secrets: dict[str, str | None] = Field(default_factory=dict)


@router.get("/me")
async def admin_my_access(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, object]:
    """Never 403s — lets the UI render the permission matrix for any member."""
    return await describe_admin_access(session, tenant)


@router.get("/audit/summary")
async def admin_audit_summary(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(require_support_audit)],
) -> dict[str, object]:
    users = await session.scalar(select(func.count()).select_from(User))
    orgs = await session.scalar(select(func.count()).select_from(Organization))
    workspaces = await session.scalar(select(func.count()).select_from(Workspace))
    return {
        "users": int(users or 0),
        "organizations": int(orgs or 0),
        "workspaces": int(workspaces or 0),
        "workspace_id": str(tenant.workspace_id),
    }


@router.get("/overview")
async def admin_overview(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(require_platform_admin)],
) -> dict[str, object]:
    await bind_workspace_rls(session, tenant)
    conversations = await session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.tenant_id == tenant.tenant_id,
            Conversation.workspace_id == tenant.workspace_id,
        )
    )
    recommendations = await session.scalar(
        select(func.count())
        .select_from(Recommendation)
        .where(
            Recommendation.tenant_id == tenant.tenant_id,
            Recommendation.workspace_id == tenant.workspace_id,
        )
    )
    return {
        "conversations": int(conversations or 0),
        "recommendations": int(recommendations or 0),
        "workspace_id": str(tenant.workspace_id),
    }


@router.get("/conversations")
async def admin_list_conversations(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(require_platform_admin)],
) -> dict[str, object]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant.tenant_id,
            Conversation.workspace_id == tenant.workspace_id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    rows = list(result.scalars().all())
    return {"items": [{"id": str(c.id), "title": c.title, "mode": c.mode.value} for c in rows]}


@router.get("/observability/agent-runs")
async def admin_agent_runs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(require_platform_admin)],
) -> dict[str, object]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == tenant.tenant_id,
            AgentRun.workspace_id == tenant.workspace_id,
        )
        .order_by(AgentRun.started_at.desc())
        .limit(25)
    )
    runs = list(result.scalars().all())
    return {
        "items": [
            {
                "id": str(r.id),
                "symbol": r.symbol,
                "status": r.status.value,
                "tool_calls": r.tool_calls_count,
                "memories_retrieved": r.memories_retrieved_count,
            }
            for r in runs
        ]
    }


@router.get("/secrets")
async def admin_list_secrets(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(require_platform_admin)],
) -> dict[str, Any]:
    """Masked secret status only — never returns plaintext values."""
    _ = tenant
    items = await list_secret_status(session)
    return status_payload(items)


@router.put("/secrets")
async def admin_upsert_secrets(
    body: AdminSecretsUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(require_platform_admin)],
) -> dict[str, Any]:
    """Upsert platform secrets from the admin panel. Applies immediately in-process."""
    try:
        items = await upsert_secrets(
            session,
            updates=body.secrets,
            actor_user_id=tenant.user_id,
        )
        await session.commit()
    except PlatformSecretError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return status_payload(items)

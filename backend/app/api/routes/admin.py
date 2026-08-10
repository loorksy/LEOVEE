from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_deps import require_platform_admin, require_support_audit
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.infrastructure.database import get_db_session
from app.models.conversation import Conversation
from app.models.learning import AgentRun
from app.models.organization import Organization
from app.models.recommendation import Recommendation
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


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

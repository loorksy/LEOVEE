from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.seed import ensure_platform_seed
from app.models.enums import WorkspaceStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember


def _slugify(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean[:48] or "workspace"


async def _unique_workspace_slug(session: AsyncSession, tenant_id: uuid.UUID, base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    suffix = 0
    while True:
        existing = await session.scalar(
            select(Workspace.id).where(
                Workspace.tenant_id == tenant_id,
                Workspace.slug == candidate,
            )
        )
        if existing is None:
            return candidate
        suffix += 1
        candidate = f"{slug}-{suffix}"


async def create_default_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    name: str | None = None,
) -> Workspace:
    user_role = await ensure_platform_seed(session)
    ws_name = name or "Default Workspace"
    workspace = Workspace(
        tenant_id=tenant_id,
        name=ws_name,
        slug=await _unique_workspace_slug(session, tenant_id, ws_name),
        owner_user_id=owner_user_id,
        settings_json={},
        status=WorkspaceStatus.ACTIVE,
    )
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            tenant_id=tenant_id,
            workspace_id=workspace.id,
            user_id=owner_user_id,
            role_id=user_role.id,
        )
    )
    from app.models.enums import PlanCode
    from app.models.plan import Plan

    plan = await session.scalar(select(Plan).where(Plan.code == PlanCode.FREE))
    if plan is not None:
        existing_sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        if existing_sub is None:
            session.add(
                Subscription(
                    tenant_id=tenant_id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    payment_provider="manual",
                )
            )
    await session.flush()
    return workspace


async def list_workspaces_for_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[Workspace]:
    result = await session.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            Workspace.tenant_id == tenant_id,
            WorkspaceMember.user_id == user_id,
        )
        .order_by(Workspace.created_at.asc())
    )
    return list(result.scalars().unique().all())


async def get_workspace_for_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Workspace | None:
    result = await session.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            Workspace.id == workspace_id,
            Workspace.tenant_id == tenant_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.infrastructure.database import get_db_session
from app.infrastructure.seed import ensure_platform_seed
from app.main import app
from app.models.billing import BillingWebhookEvent
from app.models.enums import PlanCode
from app.models.plan import Plan
from app.models.rbac import Role
from app.models.workspace_member import WorkspaceMember
from app.services import entitlement_service
from app.tests.conftest import seed_user_org


async def _set_workspace_role(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_code: str,
) -> None:
    await ensure_platform_seed(session)
    role = await session.scalar(select(Role).where(Role.code == role_code))
    assert role is not None
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    assert member is not None
    member.role_id = role.id
    await session.flush()


@pytest.mark.asyncio
async def test_admin_me_reflects_permission_matrix_for_each_role(db_session: AsyncSession) -> None:
    """`/admin/me` never 403s — the UI permission matrix relies on its capability flags."""
    user, org, _ = await seed_user_org(
        db_session, email="matrix-user@example.com", slug="matrix-user"
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    headers = {
        "X-Tenant-Id": str(org.id),
        "X-Workspace-Id": str(ctx.workspace_id),
    }
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            default_response = await client.get("/api/v1/admin/me", headers=headers)
            assert default_response.status_code == 200
            default_body = default_response.json()
            assert default_body["role"] == "USER"
            assert default_body["is_support"] is False
            assert default_body["is_platform_admin"] is False

            await _set_workspace_role(
                db_session,
                workspace_id=ctx.workspace_id,
                user_id=user.id,
                role_code="SUPPORT",
            )
            await db_session.commit()
            support_response = await client.get("/api/v1/admin/me", headers=headers)
            assert support_response.status_code == 200
            support_body = support_response.json()
            assert support_body["role"] == "SUPPORT"
            assert support_body["is_support"] is True
            assert support_body["is_platform_admin"] is False

            await _set_workspace_role(
                db_session,
                workspace_id=ctx.workspace_id,
                user_id=user.id,
                role_code="ADMIN",
            )
            await db_session.commit()
            admin_response = await client.get("/api/v1/admin/me", headers=headers)
            assert admin_response.status_code == 200
            admin_body = admin_response.json()
            assert admin_body["role"] == "ADMIN"
            assert admin_body["is_support"] is True
            assert admin_body["is_platform_admin"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_support_cannot_list_admin_conversations(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(
        db_session,
        email="support-no-chat@example.com",
        slug="support-no-chat",
    )
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await _set_workspace_role(
        db_session,
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        role_code="SUPPORT",
    )
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        audit = await client.get(
            "/api/v1/admin/audit/summary",
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
        blocked = await client.get(
            "/api/v1/admin/conversations",
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert audit.status_code == 200
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_stripe_webhook_idempotent(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, org, _ = await seed_user_org(db_session, email="wh@example.com", slug="wh-hook")
    await db_session.commit()
    monkeypatch.setenv("BILLING_PROVIDER", "test_stripe")
    from app.core.config import get_settings

    get_settings.cache_clear()
    payload = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"tenant_id": str(org.id), "plan_code": "FREE"},
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/billing/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "test"},
        )
        second = await client.post(
            "/api/v1/billing/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "test"},
        )
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json().get("duplicate") is not True
    assert second.json().get("duplicate") is True
    rows = await db_session.execute(select(BillingWebhookEvent))
    assert len(rows.scalars().all()) == 1


@pytest.mark.asyncio
async def test_analysis_run_blocked_when_monthly_limit_exceeded(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="limit@example.com", slug="limit-analysis")
    ctx = await resolve_tenant_context(db_session, user.id)
    plan = await db_session.scalar(select(Plan).where(Plan.code == PlanCode.FREE))
    assert plan is not None
    plan.limits_json = {**(plan.limits_json or {}), "analysis_runs_per_month": 1}
    await bind_workspace_rls(db_session, ctx)
    await entitlement_service.record_usage(
        db_session,
        ctx,
        "analysis.run",
        quantity=Decimal("1"),
    )
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/analysis/run",
            json={"symbol": "EURUSD", "complete_pipeline": False},
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json().get("code") == "limit_exceeded"


@pytest.mark.asyncio
async def test_billing_entitlements_endpoint(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="ent@example.com", slug="entitlements")
    ctx = await resolve_tenant_context(db_session, user.id)
    await db_session.commit()

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/billing/entitlements",
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["plan_code"] == "FREE"
    assert "limits" in body

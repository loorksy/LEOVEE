from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.enums import PlanCode
from app.models.plan import Plan
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.usage_record import UsageRecord


class EntitlementError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def get_active_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> tuple[Plan, Subscription | None]:
    sub = await session.scalar(
        select(Subscription)
        .where(
            Subscription.tenant_id == tenant_id,
            Subscription.status.in_(
                [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
            ),
        )
        .order_by(Subscription.created_at.desc())
    )
    if sub is None:
        plan = await session.scalar(select(Plan).where(Plan.code == PlanCode.FREE))
        if plan is None:
            raise EntitlementError("plan_missing", "FREE plan is not configured")
        return plan, None
    plan = await session.get(Plan, sub.plan_id)
    if plan is None:
        raise EntitlementError("plan_missing", "Subscription plan not found")
    return plan, sub


async def current_period_usage(
    session: AsyncSession,
    tenant: TenantContext,
    metric: str,
    *,
    period_start: datetime,
    period_end: datetime,
) -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(
            UsageRecord.tenant_id == tenant.tenant_id,
            UsageRecord.workspace_id == tenant.workspace_id,
            UsageRecord.metric == metric,
            UsageRecord.period_start >= period_start,
            UsageRecord.period_end <= period_end,
        )
    )
    return Decimal(str(total or 0))


async def check_metric_limit(
    session: AsyncSession,
    tenant: TenantContext,
    metric: str,
    *,
    increment: Decimal = Decimal("1"),
) -> None:
    plan, _sub = await get_active_plan(session, tenant.tenant_id)
    limits = plan.limits_json or {}
    limit_key = {
        "analysis.run": "analysis_runs_per_month",
        "chat.send": "messages_per_month",
        "mcp.call": "mcp_calls_per_month",
    }.get(metric, metric)
    cap = limits.get(limit_key)
    if cap is None:
        return
    now = datetime.now(UTC)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = await current_period_usage(
        session,
        tenant,
        metric,
        period_start=period_start,
        period_end=now,
    )
    if used + increment > Decimal(str(cap)):
        raise EntitlementError(
            "limit_exceeded",
            f"Plan limit exceeded for {limit_key}",
        )


async def record_usage(
    session: AsyncSession,
    tenant: TenantContext,
    metric: str,
    quantity: Decimal = Decimal("1"),
    metadata: dict[str, Any] | None = None,
) -> UsageRecord:
    now = datetime.now(UTC)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    row = UsageRecord(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        metric=metric,
        quantity=quantity,
        period_start=period_start,
        period_end=now,
        metadata_json=metadata or {},
    )
    session.add(row)
    await session.flush()
    return row


async def entitlements_for_tenant(
    session: AsyncSession,
    tenant: TenantContext,
) -> dict[str, Any]:
    plan, sub = await get_active_plan(session, tenant.tenant_id)
    code = plan.code.value if hasattr(plan.code, "value") else str(plan.code)
    return {
        "plan_code": code,
        "plan_name": plan.name,
        "limits": plan.limits_json,
        "features": plan.features_json,
        "subscription_status": sub.status.value if sub else "FREE",
    }

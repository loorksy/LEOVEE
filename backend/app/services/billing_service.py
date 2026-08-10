from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.models.billing import BillingWebhookEvent


async def record_webhook_event(
    session: AsyncSession,
    *,
    provider: str,
    external_event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> tuple[bool, BillingWebhookEvent]:
    """Returns (is_new, row). Duplicate event ids are ignored."""
    existing = await session.scalar(
        select(BillingWebhookEvent).where(
            BillingWebhookEvent.provider == provider,
            BillingWebhookEvent.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        return False, existing
    row = BillingWebhookEvent(
        provider=provider,
        external_event_id=external_event_id,
        event_type=event_type,
        payload_json=payload,
        processed_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return True, row


async def apply_entitlement_from_checkout(
    session: AsyncSession,
    *,
    tenant_id: str,
    plan_code: str,
) -> dict[str, Any]:
    import uuid

    from app.models.enums import PlanCode
    from app.models.plan import Plan
    from app.models.subscription import Subscription, SubscriptionStatus

    plan = await session.scalar(select(Plan).where(Plan.code == PlanCode(plan_code)))
    if plan is None:
        return {"updated": False, "reason": "unknown_plan"}
    sub = await session.scalar(
        select(Subscription).where(Subscription.tenant_id == uuid.UUID(tenant_id))
    )
    if sub is None:
        sub = Subscription(
            tenant_id=uuid.UUID(tenant_id),
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            payment_provider="stripe",
        )
        session.add(sub)
    else:
        sub.plan_id = plan.id
        sub.status = SubscriptionStatus.ACTIVE
        sub.payment_provider = "stripe"
    await session.flush()
    return {"updated": True, "plan_code": plan_code}

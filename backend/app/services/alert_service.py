from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.infrastructure.realtime import notification_broadcaster
from app.models.alert import Alert
from app.models.notification import Notification
from app.services import market_data


def evaluate_price_alert(condition: dict[str, Any], price: float) -> bool:
    op = condition.get("op", "gte")
    threshold = condition.get("price")
    if threshold is None:
        return False
    threshold_f = float(threshold)
    if op == "gte":
        return price >= threshold_f
    if op == "lte":
        return price <= threshold_f
    if op == "eq":
        return abs(price - threshold_f) < 1e-9
    return False


async def list_alerts(
    session: AsyncSession,
    tenant: TenantContext,
) -> list[Alert]:
    await bind_workspace_rls(session, tenant)
    result = await session.execute(
        select(Alert)
        .where(
            Alert.tenant_id == tenant.tenant_id,
            Alert.workspace_id == tenant.workspace_id,
            Alert.user_id == tenant.user_id,
        )
        .order_by(Alert.created_at.desc())
    )
    return list(result.scalars().all())


async def create_alert(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    alert_type: str,
    symbol_code: str | None,
    condition: dict[str, Any],
    channels: dict[str, Any],
) -> Alert:
    await bind_workspace_rls(session, tenant)
    symbol_id = None
    if symbol_code:
        symbol = await market_data.get_or_create_symbol(session, symbol_code)
        symbol_id = symbol.id
    alert = Alert(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
        type=alert_type,
        symbol_id=symbol_id,
        condition_json=condition,
        channels_json=channels,
        active=True,
    )
    session.add(alert)
    await session.flush()
    return alert


async def fan_out_notification(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    user_id: uuid.UUID,
    title: str,
    message: str,
    notification_type: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
) -> Notification:
    note = Notification(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    session.add(note)
    await session.flush()
    if tenant.workspace_id is not None:
        await notification_broadcaster.publish(
            str(tenant.workspace_id),
            {
                "event": "notification",
                "notification": {
                    "id": str(note.id),
                    "title": note.title,
                    "message": note.message,
                    "type": note.type,
                },
            },
        )
    return note


async def trigger_price_alert(
    session: AsyncSession,
    tenant: TenantContext,
    alert: Alert,
    *,
    price: float,
) -> bool:
    if not alert.active:
        return False
    if alert.type != "PRICE":
        return False
    if not evaluate_price_alert(alert.condition_json, price):
        return False
    alert.last_triggered_at = datetime.now(UTC)
    await fan_out_notification(
        session,
        tenant,
        user_id=alert.user_id,
        title="Price alert triggered",
        message=f"Condition met at price {price}",
        notification_type="alert_triggered",
        resource_type="alert",
        resource_id=alert.id,
    )
    await session.flush()
    return True


def alert_to_dict(alert: Alert) -> dict[str, Any]:
    return {
        "id": str(alert.id),
        "type": alert.type,
        "symbol_id": str(alert.symbol_id) if alert.symbol_id else None,
        "condition": alert.condition_json,
        "channels": alert.channels_json,
        "active": alert.active,
        "last_triggered_at": (
            alert.last_triggered_at.isoformat() if alert.last_triggered_at else None
        ),
    }

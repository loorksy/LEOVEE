from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.alert import Alert
from app.services import market_data


async def list_alerts(
    session: AsyncSession,
    tenant: TenantContext,
) -> list[Alert]:
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


async def trigger_alert(session: AsyncSession, alert: Alert) -> None:
    alert.last_triggered_at = datetime.now(UTC)
    await session.flush()


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

"""Market-driven alert evaluation (price conditions → notification fan-out)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.tenant import resolve_tenant_context, resolve_workspace_context
from app.models.alert import Alert
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.services import alert_service

# Avoid re-firing the same alert every cron tick while the condition remains true.
_TRIGGER_COOLDOWN = timedelta(minutes=15)


async def _latest_close_by_symbol(session: AsyncSession) -> dict[UUID, float]:
    """Return latest close per symbol_id (prefer M1, then M5, then H1)."""
    quotes: dict[UUID, float] = {}
    for timeframe in (Timeframe.M1, Timeframe.M5, Timeframe.H1):
        rows = await session.execute(
            select(Candle.symbol_id, Candle.close, Candle.ts)
            .where(Candle.timeframe == timeframe)
            .order_by(Candle.ts.desc())
        )
        for symbol_id, close, _ts in rows.all():
            if symbol_id not in quotes:
                quotes[symbol_id] = float(close)
    return quotes


def _in_cooldown(alert: Alert) -> bool:
    if alert.last_triggered_at is None:
        return False
    return utc_now() - alert.last_triggered_at < _TRIGGER_COOLDOWN


async def run_alert_evaluation_cycle(session: AsyncSession) -> dict[str, int]:
    """Evaluate active PRICE alerts against latest candle closes and fan out."""
    quotes = await _latest_close_by_symbol(session)
    result = await session.execute(
        select(Alert).where(Alert.active.is_(True), Alert.type == "PRICE")
    )
    alerts = list(result.scalars().all())
    evaluated = 0
    triggered = 0
    for alert in alerts:
        evaluated += 1
        if alert.symbol_id is None or _in_cooldown(alert):
            continue
        price = quotes.get(alert.symbol_id)
        if price is None:
            continue
        try:
            tenant = await resolve_tenant_context(
                session,
                alert.user_id,
                client_tenant_id=alert.tenant_id,
            )
            tenant = await resolve_workspace_context(
                session,
                tenant,
                client_workspace_id=alert.workspace_id,
            )
        except Exception:
            continue
        fired = await alert_service.trigger_price_alert(
            session,
            tenant,
            alert,
            price=price,
        )
        if fired:
            triggered += 1
    return {"alerts_evaluated": evaluated, "alerts_triggered": triggered}

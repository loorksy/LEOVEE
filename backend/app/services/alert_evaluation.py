"""Market-driven alert evaluation (price conditions → notification fan-out)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.tenant import (
    TenantContext,
    resolve_tenant_context,
    resolve_workspace_context,
)
from app.core.tenant_rls import bind_workspace_rls
from app.models.alert import Alert
from app.models.candle import Candle
from app.models.enums import Timeframe
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
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


async def _workspace_tenant(session: AsyncSession, workspace: Workspace) -> TenantContext | None:
    """A bound tenant context for a workspace, via any one of its members.

    None when the workspace has no members — nobody to answer for it, so it is
    skipped silently rather than reported as a failure every cron tick.
    """
    member = await session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id).limit(1)
    )
    if member is None:
        return None
    tenant = await resolve_tenant_context(
        session, member.user_id, client_tenant_id=member.tenant_id
    )
    return await resolve_workspace_context(session, tenant, client_workspace_id=workspace.id)


async def run_alert_evaluation_cycle(session: AsyncSession) -> dict[str, int]:
    """Evaluate active PRICE alerts against latest candle closes and fan out.

    Alerts are RLS-scoped, so the scan must run *bound* to a workspace — the
    same per-workspace loop the recommendation tracker uses. An earlier version
    ran one flat ``SELECT`` on an unbound session; under FORCE ROW LEVEL
    SECURITY that returns zero rows, so no alert ever fired in production. The
    quote map is read once up front from ``candles``, which is platform-global
    and needs no binding.
    """
    quotes = await _latest_close_by_symbol(session)
    evaluated = 0
    triggered = 0
    workspaces = list((await session.execute(select(Workspace))).scalars().all())
    for workspace in workspaces:
        try:
            tenant = await _workspace_tenant(session, workspace)
            if tenant is None:
                continue
            await bind_workspace_rls(session, tenant)
            alerts = list(
                (
                    await session.execute(
                        select(Alert).where(Alert.active.is_(True), Alert.type == "PRICE")
                    )
                )
                .scalars()
                .all()
            )
            for alert in alerts:
                evaluated += 1
                if alert.symbol_id is None or _in_cooldown(alert):
                    continue
                price = quotes.get(alert.symbol_id)
                if price is None:
                    continue
                fired = await alert_service.trigger_price_alert(session, tenant, alert, price=price)
                if fired:
                    triggered += 1
        except Exception:
            # One workspace's failure must not abort the sweep; the session may
            # be poisoned by the failed statement, so roll back to a usable state.
            await session.rollback()
            continue
    return {"alerts_evaluated": evaluated, "alerts_triggered": triggered}

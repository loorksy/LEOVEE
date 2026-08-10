from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.enums import RecommendationDirection, TradeStatus
from app.models.trade import Trade
from app.services import market_data


async def list_trades(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    limit: int = 50,
) -> list[Trade]:
    result = await session.execute(
        select(Trade)
        .where(
            Trade.tenant_id == tenant.tenant_id,
            Trade.workspace_id == tenant.workspace_id,
        )
        .order_by(Trade.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_trade_idea(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    symbol_code: str,
    direction: RecommendationDirection,
    entry: Decimal | None = None,
    stop: Decimal | None = None,
    targets: list[float] | None = None,
    recommendation_id: uuid.UUID | None = None,
    execution_enabled: bool = False,
) -> Trade:
    if execution_enabled:
        raise ValueError("execution_disabled_by_policy")
    symbol = await market_data.get_or_create_symbol(session, symbol_code)
    trade = Trade(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol_id=symbol.id,
        direction=direction,
        status=TradeStatus.IDEA,
        entry=entry,
        stop=stop,
        targets_json=targets or [],
        recommendation_id=recommendation_id,
        execution_enabled=False,
    )
    session.add(trade)
    await session.flush()
    return trade


def trade_to_dict(trade: Trade, *, symbol_code: str | None = None) -> dict[str, Any]:
    return {
        "id": str(trade.id),
        "symbol_id": str(trade.symbol_id),
        "symbol": symbol_code,
        "direction": trade.direction.value,
        "status": trade.status.value,
        "entry": float(trade.entry) if trade.entry is not None else None,
        "stop": float(trade.stop) if trade.stop is not None else None,
        "targets": trade.targets_json,
        "execution_enabled": trade.execution_enabled,
        "recommendation_id": str(trade.recommendation_id) if trade.recommendation_id else None,
    }

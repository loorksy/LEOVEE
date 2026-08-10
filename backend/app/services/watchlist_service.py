from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.symbol import Symbol
from app.models.watchlist import Watchlist, WatchlistItem
from app.services import market_data


async def list_watchlists(
    session: AsyncSession,
    tenant: TenantContext,
) -> list[Watchlist]:
    result = await session.execute(
        select(Watchlist)
        .where(
            Watchlist.tenant_id == tenant.tenant_id,
            Watchlist.workspace_id == tenant.workspace_id,
        )
        .order_by(Watchlist.sort_order, Watchlist.name)
    )
    return list(result.scalars().all())


async def create_watchlist(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    name: str,
) -> Watchlist:
    wl = Watchlist(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        name=name,
    )
    session.add(wl)
    await session.flush()
    return wl


async def add_symbol(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    watchlist_id: uuid.UUID,
    symbol_code: str,
) -> WatchlistItem:
    wl = await session.scalar(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.tenant_id == tenant.tenant_id,
            Watchlist.workspace_id == tenant.workspace_id,
        )
    )
    if wl is None:
        raise LookupError("watchlist_not_found")
    symbol = await market_data.get_or_create_symbol(session, symbol_code)
    existing = await session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol_id == symbol.id,
        )
    )
    if existing is not None:
        return existing
    item = WatchlistItem(watchlist_id=watchlist_id, symbol_id=symbol.id)
    session.add(item)
    await session.flush()
    return item


async def watchlist_items(
    session: AsyncSession,
    watchlist_id: uuid.UUID,
) -> list[tuple[WatchlistItem, Symbol]]:
    result = await session.execute(
        select(WatchlistItem, Symbol)
        .join(Symbol, Symbol.id == WatchlistItem.symbol_id)
        .where(WatchlistItem.watchlist_id == watchlist_id)
        .order_by(WatchlistItem.sort_order)
    )
    return list(result.all())


def watchlist_to_dict(
    wl: Watchlist,
    items: list[tuple[WatchlistItem, Symbol]],
) -> dict[str, Any]:
    return {
        "id": str(wl.id),
        "name": wl.name,
        "symbols": [{"code": sym.code, "item_id": str(item.id)} for item, sym in items],
    }

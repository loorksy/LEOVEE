from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.symbol import Symbol
from app.models.watchlist import Watchlist, WatchlistItem
from app.services import market_data


async def list_watchlists(
    session: AsyncSession,
    tenant: TenantContext,
) -> list[Watchlist]:
    await bind_workspace_rls(session, tenant)
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
    await bind_workspace_rls(session, tenant)
    wl = Watchlist(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        name=name,
    )
    session.add(wl)
    await session.flush()
    return wl


async def delete_watchlist(
    session: AsyncSession,
    tenant: TenantContext,
    watchlist_id: uuid.UUID,
) -> bool:
    await bind_workspace_rls(session, tenant)
    wl = await session.scalar(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.tenant_id == tenant.tenant_id,
            Watchlist.workspace_id == tenant.workspace_id,
        )
    )
    if wl is None:
        return False
    await session.delete(wl)
    await session.flush()
    return True


async def add_symbol(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    watchlist_id: uuid.UUID,
    symbol_code: str,
) -> WatchlistItem:
    await bind_workspace_rls(session, tenant)
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
    return list(result.all())  # type: ignore[arg-type]


def watchlist_to_dict(
    wl: Watchlist,
    items: list[tuple[WatchlistItem, Symbol]],
    *,
    quotes: dict[str, float] | None = None,
) -> dict[str, Any]:
    quotes = quotes or {}
    return {
        "id": str(wl.id),
        "name": wl.name,
        "symbols": [
            {
                "code": sym.code,
                "item_id": str(item.id),
                "last_price": quotes.get(sym.code),
            }
            for item, sym in items
        ],
    }


async def collect_watchlist_symbol_codes(
    session: AsyncSession,
    tenant: TenantContext,
) -> list[str]:
    lists = await list_watchlists(session, tenant)
    codes: list[str] = []
    for wl in lists:
        for _item, sym in await watchlist_items(session, wl.id):
            codes.append(sym.code)
    return sorted(set(codes))


async def latest_quotes_for_workspace(
    session: AsyncSession,
    tenant: TenantContext,
) -> dict[str, float]:
    from app.models.candle import Candle
    from app.models.enums import Timeframe

    codes = await collect_watchlist_symbol_codes(session, tenant)
    if not codes:
        return {}
    result = await session.execute(select(Symbol).where(Symbol.code.in_(codes)))
    symbols = {s.code: s.id for s in result.scalars().all()}
    quotes: dict[str, float] = {}
    for code, symbol_id in symbols.items():
        row = await session.scalar(
            select(Candle)
            .where(Candle.symbol_id == symbol_id, Candle.timeframe == Timeframe.H1)
            .order_by(Candle.ts.desc())
            .limit(1)
        )
        if row is not None:
            quotes[code] = float(row.close)
    return quotes

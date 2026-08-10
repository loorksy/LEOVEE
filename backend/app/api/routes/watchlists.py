from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.services import watchlist_service

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class WatchlistSymbolAdd(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)


@router.get("")
async def list_watchlists(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    with_quotes: bool = False,
) -> dict[str, Any]:
    lists = await watchlist_service.list_watchlists(session, tenant)
    quotes: dict[str, float] = {}
    if with_quotes:
        quotes = await watchlist_service.latest_quotes_for_workspace(session, tenant)
    payload: list[dict[str, Any]] = []
    for wl in lists:
        items = await watchlist_service.watchlist_items(session, wl.id)
        payload.append(
            watchlist_service.watchlist_to_dict(wl, items, quotes=quotes if with_quotes else None)
        )
    symbol_codes = await watchlist_service.collect_watchlist_symbol_codes(session, tenant)
    return {"items": payload, "ws_symbols": symbol_codes}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    body: WatchlistCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    wl = await watchlist_service.create_watchlist(session, tenant, name=body.name)
    return {"id": str(wl.id)}


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> None:
    deleted = await watchlist_service.delete_watchlist(session, tenant, watchlist_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")


@router.post("/{watchlist_id}/symbols", status_code=status.HTTP_201_CREATED)
async def add_watchlist_symbol(
    watchlist_id: uuid.UUID,
    body: WatchlistSymbolAdd,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    try:
        item = await watchlist_service.add_symbol(
            session,
            tenant,
            watchlist_id=watchlist_id,
            symbol_code=body.symbol.upper(),
        )
    except LookupError as exc:
        if str(exc) == "watchlist_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found"
            ) from exc
        raise
    return {"id": str(item.id)}

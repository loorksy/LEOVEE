from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.enums import Timeframe
from app.services import market_data

router = APIRouter(prefix="/api/v1/markets", tags=["markets"])


@router.get("/{symbol}/candles")
async def get_candles_snapshot(
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    timeframe: Timeframe = Timeframe.H1,
    count: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    sym, candles = await market_data.fetch_and_store_candles(
        session,
        symbol_code=symbol.upper(),
        timeframe=timeframe,
        count=count,
    )
    return {
        "symbol": sym.code,
        "timeframe": timeframe.value,
        "workspace_id": str(tenant.workspace_id),
        "candles": [market_data.candle_to_dict(c) for c in candles],
    }

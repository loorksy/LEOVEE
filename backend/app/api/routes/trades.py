from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.enums import RecommendationDirection
from app.models.symbol import Symbol
from app.services import trade_service

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


class TradeCreate(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    direction: RecommendationDirection
    entry: float | None = None
    stop: float | None = None
    targets: list[float] = Field(default_factory=list)
    recommendation_id: str | None = None
    execution_enabled: bool = False


@router.get("")
async def list_trades(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    rows = await trade_service.list_trades(session, tenant)
    symbol_ids = {t.symbol_id for t in rows}
    symbols: dict[uuid.UUID, str] = {}
    if symbol_ids:
        result = await session.execute(select(Symbol).where(Symbol.id.in_(symbol_ids)))
        symbols = {s.id: s.code for s in result.scalars().all()}
    return {
        "items": [
            trade_service.trade_to_dict(t, symbol_code=symbols.get(t.symbol_id)) for t in rows
        ]
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_trade(
    body: TradeCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    from decimal import Decimal

    rec_id = uuid.UUID(body.recommendation_id) if body.recommendation_id else None
    try:
        trade = await trade_service.create_trade_idea(
            session,
            tenant,
            symbol_code=body.symbol.upper(),
            direction=body.direction,
            entry=Decimal(str(body.entry)) if body.entry is not None else None,
            stop=Decimal(str(body.stop)) if body.stop is not None else None,
            targets=body.targets,
            recommendation_id=rec_id,
            execution_enabled=body.execution_enabled,
        )
    except ValueError as exc:
        if str(exc) == "execution_disabled_by_policy":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Live execution is disabled",
            ) from exc
        raise
    await session.commit()
    return {"id": str(trade.id)}

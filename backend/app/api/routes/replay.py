from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.enums import Timeframe
from app.models.memory import AgentMemory
from app.services import market_data, replay_service

router = APIRouter(prefix="/api/v1/replay", tags=["replay"])


class ReplayRunRequest(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    as_of: datetime
    timeframe: Timeframe = Timeframe.H1


@router.post("/run")
async def run_replay(
    body: ReplayRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    symbol, candles = await market_data.fetch_and_store_candles(
        session,
        symbol_code=body.symbol.upper(),
        timeframe=body.timeframe,
        count=200,
    )
    mem_result = await session.execute(
        select(AgentMemory).where(
            AgentMemory.tenant_id == tenant.tenant_id,
            AgentMemory.workspace_id == tenant.workspace_id,
        )
    )
    memories = list(mem_result.scalars().all())
    try:
        snapshot = replay_service.build_replay_snapshot(
            as_of=body.as_of,
            candles=candles,
            memories=memories,
            symbol=symbol.code,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    await session.commit()
    return snapshot

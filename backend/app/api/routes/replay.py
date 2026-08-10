from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.enums import Timeframe
from app.services import replay_service

router = APIRouter(prefix="/api/v1/replay", tags=["replay"])


class ReplayPreviewRequest(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    timeframe: Timeframe = Timeframe.H1
    as_of: datetime = Field(description="Replay clock T (ISO-8601); no data after T is returned")


@router.post("/preview")
async def replay_preview(
    body: ReplayPreviewRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    return await replay_service.preview_replay(
        session,
        tenant,
        symbol=body.symbol.upper(),
        timeframe=body.timeframe,
        as_of=body.as_of,
    )

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.models.enums import Timeframe
from app.services import analysis_service

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


class AnalysisRunRequest(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    timeframe: Timeframe = Timeframe.H1


@router.post("/run")
async def run_analysis_endpoint(
    body: AnalysisRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    return await analysis_service.run_analysis(
        session,
        tenant,
        symbol=body.symbol.upper(),
        timeframe=body.timeframe,
    )

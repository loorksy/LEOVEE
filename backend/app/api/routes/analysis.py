from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.symbols import DEFAULT_SYMBOL
from app.core.tenant import TenantContext
from app.core.timeframes import DEFAULT_SERIES_TIMEFRAME, is_decision_timeframe
from app.infrastructure.database import get_db_session
from app.models.enums import Timeframe
from app.services import analysis_service

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


class AnalysisRunRequest(BaseModel):
    """Symbol is optional because there is only one, and timeframe is optional
    because choosing it is the agent's job, not the caller's.

    Leovee trades scalp only, and which of M1/M5/M15 carries the setup is an
    analytical judgement about where structure is legible — see
    app/core/timeframes.py. A caller *may* still pin a frame (the chart passes
    the one it is displaying), but it has to be one a scalp can live on; a
    request for H4 is asking for a different trade, not a slower view of this
    one.
    """

    symbol: str = Field(default=DEFAULT_SYMBOL, min_length=3, max_length=12)
    timeframe: Timeframe | None = Field(
        default=None,
        description="Optional. Omit to let the agent choose within the scalping range.",
    )
    complete_pipeline: bool = Field(
        default=False,
        description="When true: reasoning → recommendation → thesis in one transaction",
    )


@router.post("/run")
async def run_analysis_endpoint(
    body: AnalysisRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    timeframe = body.timeframe or DEFAULT_SERIES_TIMEFRAME
    if not is_decision_timeframe(timeframe):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{timeframe.value} is not a scalping timeframe. "
                "Leovee decides on M1, M5 or M15; higher frames are context only."
            ),
        )
    return await analysis_service.run_analysis(
        session,
        tenant,
        symbol=body.symbol.upper(),
        timeframe=timeframe,
        complete_pipeline=body.complete_pipeline,
    )

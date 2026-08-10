from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.services import alert_service

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    symbol: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    channels: dict[str, Any] = Field(default_factory=lambda: {"in_app": True})


@router.get("")
async def list_alerts(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    rows = await alert_service.list_alerts(session, tenant)
    return {"items": [alert_service.alert_to_dict(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    alert = await alert_service.create_alert(
        session,
        tenant,
        alert_type=body.type,
        symbol_code=body.symbol.upper() if body.symbol else None,
        condition=body.condition,
        channels=body.channels,
    )
    await session.commit()
    return {"id": str(alert.id)}


@router.post("/{alert_id}/trigger")
async def trigger_alert_mock(
    alert_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, str]:
    from sqlalchemy import select

    from app.models.alert import Alert

    alert = await session.scalar(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.tenant_id == tenant.tenant_id,
            Alert.workspace_id == tenant.workspace_id,
        )
    )
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    await alert_service.trigger_alert(session, alert)
    await session.commit()
    return {"status": "triggered"}

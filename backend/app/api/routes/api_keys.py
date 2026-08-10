from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.services import api_key_service

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    scopes: list[str] = Field(
        default_factory=lambda: sorted(["workspace.read", "markets.read"]),
    )


@router.get("")
async def list_keys(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, object]:
    rows = await api_key_service.list_api_keys(session, tenant)
    return {
        "items": [
            {
                "id": str(row.id),
                "name": row.name,
                "key_prefix": row.key_prefix,
                "scopes": row.scopes,
                "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            }
            for row in rows
        ]
    }


@router.post("")
async def create_key(
    body: CreateApiKeyRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, object]:
    row, plain = await api_key_service.create_api_key(
        session,
        tenant,
        name=body.name,
        scopes=body.scopes,
    )
    return {
        "id": str(row.id),
        "name": row.name,
        "key_prefix": row.key_prefix,
        "scopes": row.scopes,
        "api_key": plain,
    }


@router.delete("/{key_id}")
async def revoke_key(
    key_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> dict[str, object]:
    revoked = await api_key_service.revoke_api_key(session, tenant, key_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"revoked": True}

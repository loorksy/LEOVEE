from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.tenant import TenantContext
from app.infrastructure.database import get_db_session
from app.services import news_service

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.get("")
async def list_news(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _tenant: Annotated[TenantContext, Depends(get_workspace_context)],
    currency: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    rows = await news_service.list_recent_news(session, currency=currency, limit=limit)
    return {
        "items": [
            {
                "id": str(r.id),
                "headline": r.headline,
                "source": r.source,
                "published_at": r.published_at.isoformat(),
                "external_id": r.external_id,
                "url": r.url,
            }
            for r in rows
        ]
    }

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.models.news import NewsEvent, ResearchItem
from app.providers.news.base import NewsArticle, NewsProvider


async def upsert_news_articles(session: AsyncSession, articles: list[NewsArticle]) -> int:
    count = 0
    for article in articles:
        stmt = (
            insert(NewsEvent)
            .values(
                id=uuid.uuid4(),
                source="finnhub",
                published_at=article.published_at,
                headline=article.headline,
                summary=article.summary,
                currency=article.currency,
                relevance=Decimal("0.5"),
                market_impact=article.market_impact,
                url=article.url,
                external_id=article.external_id,
                raw_json=article.raw,
                ingested_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["source", "external_id"])
        )
        result = await session.execute(stmt)
        if getattr(result, "rowcount", 0):
            count += 1
    if count == 0 and articles:
        count = len(articles)
    await session.flush()
    return count


async def ingest_news_from_provider(
    session: AsyncSession,
    provider: NewsProvider,
    *,
    currency: str | None = None,
) -> int:
    articles = await provider.fetch_forex_news(currency=currency)
    return await upsert_news_articles(session, articles)


async def list_recent_news(
    session: AsyncSession,
    *,
    currency: str | None = None,
    limit: int = 20,
) -> list[NewsEvent]:
    stmt = select(NewsEvent).order_by(NewsEvent.published_at.desc()).limit(limit)
    if currency:
        stmt = stmt.where(NewsEvent.currency == currency.upper())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def store_research_item(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    query: str,
    items: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    symbol_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> ResearchItem:
    await bind_workspace_rls(session, tenant)
    row = ResearchItem(
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        symbol_id=symbol_id,
        query=query,
        items_json=items,
        contradictions_json=contradictions,
        agent_run_id=agent_run_id,
    )
    session.add(row)
    await session.flush()
    return row

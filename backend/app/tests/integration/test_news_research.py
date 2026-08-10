from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.research_agent import run_research_agent
from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.news import NewsEvent, ResearchItem
from app.providers.news.base import NewsArticle
from app.services import news_service
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_news_upsert_requires_provenance_fields(db_session: AsyncSession) -> None:
    article = NewsArticle(
        external_id="ext-1",
        headline="Fed speaks",
        summary="Summary",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        currency="USD",
        url="https://example.com/a",
        market_impact="HIGH",
        raw={"id": "ext-1"},
    )
    inserted = await news_service.upsert_news_articles(db_session, [article])
    assert inserted >= 1
    row = await db_session.scalar(select(NewsEvent).where(NewsEvent.external_id == "ext-1"))
    assert row is not None
    assert row.source == "finnhub"
    assert row.headline == "Fed speaks"


@pytest.mark.asyncio
async def test_research_agent_persists_workspace_item(db_session: AsyncSession) -> None:
    user, _org, _m = await seed_user_org(db_session)
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)

    event = NewsEvent(
        id=uuid.uuid4(),
        source="finnhub",
        published_at=datetime(2026, 2, 1, tzinfo=UTC),
        headline="EUR volatility",
        summary="test",
        currency="EUR",
        relevance=None,
        market_impact="LOW",
        url=None,
        external_id="eur-1",
        raw_json={"id": "eur-1"},
    )
    db_session.add(event)
    await db_session.flush()

    output = run_research_agent(query="EUR outlook", news=[event])
    item = await news_service.store_research_item(
        db_session,
        ctx,
        query=output["query"],
        items=output["items"],
        contradictions=output["contradictions"],
    )
    await db_session.commit()

    await bind_workspace_rls(db_session, ctx)
    stored = await db_session.scalar(select(ResearchItem).where(ResearchItem.id == item.id))
    assert stored is not None
    assert output["items"][0]["provenance"]["external_id"] == "eur-1"
    assert stored.query == "EUR outlook"

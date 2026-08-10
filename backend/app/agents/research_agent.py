from __future__ import annotations

from typing import Any

from app.models.news import NewsEvent


def run_research_agent(
    *,
    query: str,
    news: list[NewsEvent],
) -> dict[str, Any]:
    """
    Deterministic research pass: provenance-bearing items + simple contradiction scan.
    LLM enrichment arrives in later phases; no live model required here.
    """
    items: list[dict[str, Any]] = []
    for article in news:
        items.append(
            {
                "headline": article.headline,
                "source": article.source,
                "external_id": article.external_id,
                "published_at": article.published_at.isoformat(),
                "url": article.url,
                "provenance": {
                    "provider": article.source,
                    "external_id": article.external_id,
                    "ingested_at": article.ingested_at.isoformat(),
                },
            }
        )

    impacts = {a.market_impact for a in news if a.market_impact}
    contradictions: list[dict[str, Any]] = []
    if "HIGH" in impacts and "LOW" in impacts:
        contradictions.append(
            {
                "type": "IMPACT_MISMATCH",
                "detail": "Mixed HIGH and LOW impact headlines in window",
            }
        )

    return {
        "query": query,
        "items": items,
        "contradictions": contradictions,
        "summary": f"Found {len(items)} sourced items for: {query}",
    }

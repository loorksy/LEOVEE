from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import DataUnavailableError
from app.providers.news.base import NewsArticle


class FinnhubNewsProvider:
    """Finnhub forex/market news adapter (Phase 14)."""

    def __init__(self, settings: Settings | None = None) -> None:
        resolved = settings or get_settings()
        if not resolved.finnhub_api_key:
            raise DataUnavailableError("FINNHUB_API_KEY is not configured")
        self._key = resolved.finnhub_api_key
        self._base = "https://finnhub.io/api/v1"

    async def fetch_forex_news(
        self,
        *,
        currency: str | None = None,
        limit: int = 50,
    ) -> list[NewsArticle]:
        params: dict[str, str] = {"token": self._key, "category": "forex"}
        if currency:
            params["q"] = currency
        url = f"{self._base}/news"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 429:
                raise DataUnavailableError("Finnhub rate limit exceeded")
            response.raise_for_status()
            payload: list[dict[str, Any]] = response.json()

        articles: list[NewsArticle] = []
        for item in payload[:limit]:
            ts = datetime.fromtimestamp(item.get("datetime", 0), tz=UTC)
            articles.append(
                NewsArticle(
                    external_id=str(item.get("id", item.get("url", ts.isoformat()))),
                    headline=str(item.get("headline", "")),
                    summary=item.get("summary"),
                    published_at=ts,
                    currency=currency,
                    url=item.get("url"),
                    market_impact=None,
                    raw=item,
                )
            )
        return articles


def get_news_provider(settings: Settings | None = None) -> FinnhubNewsProvider:
    return FinnhubNewsProvider(settings)

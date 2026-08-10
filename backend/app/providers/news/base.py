from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class NewsArticle:
    external_id: str
    headline: str
    summary: str | None
    published_at: datetime
    currency: str | None
    url: str | None
    market_impact: str | None
    raw: dict[str, Any]


class NewsProvider(Protocol):
    async def fetch_forex_news(
        self,
        *,
        currency: str | None = None,
        limit: int = 50,
    ) -> list[NewsArticle]: ...

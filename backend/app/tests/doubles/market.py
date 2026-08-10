from __future__ import annotations

from app.core.errors import DataUnavailableError
from app.providers.market.base import NormalizedCandle


class FakeMarketDataProvider:
    """Test double — never used in application code."""

    def __init__(self, candles: list[NormalizedCandle] | None = None) -> None:
        self._candles = candles

    async def fetch_candles(
        self,
        instrument: str,
        *,
        granularity: str,
        count: int = 100,
    ) -> list[NormalizedCandle]:
        if self._candles is not None:
            return self._candles[:count]
        raise DataUnavailableError(
            "Synthetic market data is disabled in tests without explicit fixtures"
        )

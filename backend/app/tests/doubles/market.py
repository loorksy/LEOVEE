from __future__ import annotations

from datetime import datetime

from app.core.errors import DataUnavailableError
from app.providers.market.base import MAX_CANDLES_PER_REQUEST, NormalizedCandle


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

    async def fetch_candles_from(
        self,
        instrument: str,
        *,
        granularity: str,
        start: datetime,
        count: int = MAX_CANDLES_PER_REQUEST,
    ) -> list[NormalizedCandle]:
        """Candles at or after `start`, so a paginating backfill terminates.

        Returning the whole fixture regardless of `start` would make the
        backfill loop forever: it advances its cursor to the newest candle
        received and stops when a page brings nothing newer.
        """
        if self._candles is None:
            raise DataUnavailableError(
                "Synthetic market data is disabled in tests without explicit fixtures"
            )
        return [candle for candle in self._candles if candle.ts >= start][:count]

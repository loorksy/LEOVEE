from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import DataUnavailableError
from app.providers.market.base import (
    MAX_CANDLES_PER_REQUEST,
    MarketDataProvider,
    NormalizedCandle,
    normalize_oanda_candle,
)

# Internal Timeframe values → OANDA REST granularity codes
_OANDA_GRANULARITY: dict[str, str] = {
    "D1": "D",
}


def _oanda_granularity(internal: str) -> str:
    return _OANDA_GRANULARITY.get(internal, internal)


class OandaMarketDataProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.oanda_api_token:
            raise DataUnavailableError("OANDA API token is not configured")
        self._settings = settings
        self._base_url = settings.oanda_rest_base_url
        self._token = settings.oanda_api_token

    async def fetch_candles(
        self,
        instrument: str,
        *,
        granularity: str,
        count: int = 100,
    ) -> list[NormalizedCandle]:
        return await self._request(
            instrument,
            granularity=granularity,
            params={"count": str(min(count, MAX_CANDLES_PER_REQUEST))},
        )

    async def fetch_candles_from(
        self,
        instrument: str,
        *,
        granularity: str,
        start: datetime,
        count: int = MAX_CANDLES_PER_REQUEST,
    ) -> list[NormalizedCandle]:
        return await self._request(
            instrument,
            granularity=granularity,
            params={
                "from": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                "count": str(min(count, MAX_CANDLES_PER_REQUEST)),
                # Without this OANDA omits the still-forming candle, which is
                # the one the live stream is about to complete.
                "includeFirst": "true",
            },
        )

    async def _request(
        self,
        instrument: str,
        *,
        granularity: str,
        params: dict[str, str],
    ) -> list[NormalizedCandle]:
        oanda_instrument = instrument if "_" in instrument else f"{instrument[:3]}_{instrument[3:]}"
        oanda_granularity = _oanda_granularity(granularity)
        url = f"{self._base_url}/v3/instruments/{oanda_instrument}/candles"
        query = {"granularity": oanda_granularity, "price": "M", **params}
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=query, headers=headers)
            if response.status_code == 429:
                raise DataUnavailableError("OANDA REST rate limit exceeded")
            response.raise_for_status()
            payload = response.json()

        candles = payload.get("candles", [])
        return [normalize_oanda_candle(oanda_instrument, granularity, c) for c in candles]


def get_market_provider(settings: Settings | None = None) -> MarketDataProvider:
    resolved = settings or get_settings()
    return OandaMarketDataProvider(resolved)

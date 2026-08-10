from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import DataUnavailableError
from app.providers.market.base import MarketDataProvider, NormalizedCandle, normalize_oanda_candle


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
        oanda_instrument = instrument if "_" in instrument else f"{instrument[:3]}_{instrument[3:]}"
        url = f"{self._base_url}/v3/instruments/{oanda_instrument}/candles"
        params = {"granularity": granularity, "count": str(count), "price": "M"}
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 429:
                raise DataUnavailableError("OANDA REST rate limit exceeded")
            response.raise_for_status()
            payload = response.json()

        candles = payload.get("candles", [])
        return [normalize_oanda_candle(oanda_instrument, granularity, c) for c in candles]


def get_market_provider(settings: Settings | None = None) -> MarketDataProvider:
    resolved = settings or get_settings()
    return OandaMarketDataProvider(resolved)

from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.providers.market.base import MarketDataProvider, NormalizedCandle, normalize_oanda_candle


class OandaMarketDataProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._base_url = getattr(self._settings, "oanda_api_url", None) or "https://api-fxpractice.oanda.com"
        self._token = getattr(self._settings, "oanda_api_token", None)

    async def fetch_candles(
        self,
        instrument: str,
        *,
        granularity: str,
        count: int = 100,
    ) -> list[NormalizedCandle]:
        if not self._token:
            return _mock_candles(instrument, granularity, count)

        oanda_instrument = instrument if "_" in instrument else f"{instrument[:3]}_{instrument[3:]}"
        url = f"{self._base_url}/v3/instruments/{oanda_instrument}/candles"
        params = {"granularity": granularity, "count": str(count), "price": "M"}
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        candles = payload.get("candles", [])
        return [normalize_oanda_candle(oanda_instrument, granularity, c) for c in candles]


def _mock_candles(instrument: str, granularity: str, count: int) -> list[NormalizedCandle]:
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.models.enums import Timeframe
    from app.providers.market.base import GRANULARITY_TO_TIMEFRAME

    tf = GRANULARITY_TO_TIMEFRAME.get(granularity, Timeframe.H1)
    base = Decimal("1.10000")
    now = datetime.now(UTC)
    result: list[NormalizedCandle] = []
    for i in range(count):
        ts = now - timedelta(hours=count - i)
        price = base + Decimal(i) * Decimal("0.0001")
        result.append(
            NormalizedCandle(
                symbol=instrument.replace("_", ""),
                timeframe=tf,
                ts=ts,
                open=price,
                high=price + Decimal("0.0005"),
                low=price - Decimal("0.0005"),
                close=price + Decimal("0.0002"),
                volume=Decimal("100"),
                complete=True,
                source="mock",
            )
        )
    return result


def get_market_provider(settings: Settings | None = None) -> MarketDataProvider:
    return OandaMarketDataProvider(settings)

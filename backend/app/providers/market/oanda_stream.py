from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.core.config import Settings
from app.core.errors import DataUnavailableError
from app.services.market.candle_aggregator import CandleAggregator, PriceTick


class OandaPricingStream:
    """OANDA v20 pricing stream with reconnect/backoff and REST fallback hooks."""

    def __init__(self, settings: Settings, instruments: list[str]) -> None:
        if not settings.oanda_api_token:
            raise DataUnavailableError("OANDA API token is not configured")
        self._settings = settings
        self._instruments = instruments
        self._aggregator = CandleAggregator(timeframe_minutes=1)

    async def stream_ticks(self) -> AsyncIterator[PriceTick]:
        instrument_param = ",".join(self._instruments)
        url = (
            f"{self._settings.oanda_stream_base_url}/v3/accounts/{self._account_id}/pricing/stream"
        )
        headers = {"Authorization": f"Bearer {self._settings.oanda_api_token}"}
        params = {"instruments": instrument_param}
        backoff = 1.0
        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "GET", url, headers=headers, params=params
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            tick = self._parse_line(line)
                            if tick is not None:
                                yield tick
                backoff = 1.0
            except Exception:
                jitter = random.uniform(0, 0.5)
                await asyncio.sleep(min(backoff + jitter, 60.0))
                backoff = min(backoff * 2, 60.0)

    @property
    def _account_id(self) -> str:
        # Practice account id must be supplied via settings in production deployments.
        account = self._settings.oanda_account_id
        if not account:
            raise DataUnavailableError("OANDA account id is not configured for streaming")
        return str(account)

    def _parse_line(self, line: str) -> PriceTick | None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        if payload.get("type") != "PRICE":
            return None
        bids = payload.get("bids") or []
        asks = payload.get("asks") or []
        if not bids or not asks:
            return None
        bid = Decimal(bids[0]["price"])
        ask = Decimal(asks[0]["price"])
        ts_raw = payload.get("time")
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else datetime.now(UTC)
        instrument = payload.get("instrument", "").replace("_", "")
        return PriceTick(symbol=instrument, bid=bid, ask=ask, ts=ts)

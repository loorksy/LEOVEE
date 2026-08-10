from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

from app.core.config import Settings, get_settings
from app.core.errors import DataUnavailableError
from app.providers.market.oanda import OandaMarketDataProvider
from app.providers.market.oanda_stream import OandaPricingStream
from app.services.market.candle_aggregator import (
    CandleAggregator,
    LiveCandle,
    PriceTick,
    backfill_missing_ranges,
)


class OandaStreamManager:
    """
    OANDA pricing stream with REST fallback while disconnected and gap backfill after reconnect.
    """

    def __init__(
        self,
        settings: Settings,
        instruments: list[str],
        *,
        timeframe_minutes: int = 1,
    ) -> None:
        self._settings = settings
        self._instruments = instruments
        self._aggregator = CandleAggregator(timeframe_minutes=timeframe_minutes)
        self._rest = OandaMarketDataProvider(settings)
        self._stream = OandaPricingStream(settings, instruments)
        self._last_tick_ts: dict[str, datetime] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def ticks_with_fallback(self) -> AsyncIterator[PriceTick]:
        stream_iter = self._stream.stream_ticks().__aiter__()
        while True:
            try:
                tick = await asyncio.wait_for(stream_iter.__anext__(), timeout=30.0)
                self._connected = True
                self._last_tick_ts[tick.symbol] = tick.ts
                yield tick
            except TimeoutError:
                self._connected = False
                async for tick in self._rest_fallback_ticks():
                    yield tick
            except StopAsyncIteration:
                self._connected = False
                await asyncio.sleep(0.1)

    async def _rest_fallback_ticks(self) -> AsyncIterator[PriceTick]:
        """Poll REST pricing when stream is unavailable (rate-limit aware)."""
        for instrument in self._instruments:
            try:
                candles = await self._rest.fetch_candles(
                    instrument,
                    granularity="M1",
                    count=1,
                )
            except DataUnavailableError:
                continue
            if not candles:
                continue
            last = candles[-1]
            mid = Decimal(str(float(last.close)))
            ts = last.ts if last.ts.tzinfo else last.ts.replace(tzinfo=UTC)
            yield PriceTick(symbol=instrument.replace("_", ""), bid=mid, ask=mid, ts=ts)
            await asyncio.sleep(0.25)

    def ingest_tick(self, tick: PriceTick) -> tuple[LiveCandle | None, LiveCandle | None]:
        return self._aggregator.ingest_tick(tick)

    async def backfill_gaps(self, symbol: str) -> list[datetime]:
        last = self._last_tick_ts.get(symbol)
        if last is None:
            return []
        return backfill_missing_ranges(
            last_ts=last,
            now=datetime.now(UTC),
            timeframe_minutes=self._aggregator.timeframe_minutes,
        )


def get_stream_manager(instruments: list[str]) -> OandaStreamManager:
    return OandaStreamManager(get_settings(), instruments)

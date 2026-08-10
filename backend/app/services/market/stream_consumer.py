from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.infrastructure.realtime import candle_broadcaster
from app.models.enums import Timeframe
from app.providers.market.base import NormalizedCandle
from app.services import market_data
from app.services.market.candle_aggregator import LiveCandle
from app.services.market.stream_manager import OandaStreamManager


def live_candle_to_normalized(candle: LiveCandle) -> NormalizedCandle:
    tf = Timeframe.M1 if candle.timeframe_minutes == 1 else Timeframe.H1
    return NormalizedCandle(
        symbol=candle.symbol,
        timeframe=tf,
        ts=candle.ts,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=Decimal("0"),
        complete=candle.complete,
        source="oanda_stream",
    )


class OandaCandleStreamConsumer:
    """Connects OANDA pricing stream, aggregates ticks, persists candles, publishes realtime."""

    def __init__(
        self,
        settings: Settings,
        instruments: list[str],
        *,
        stream_manager: OandaStreamManager | None = None,
    ) -> None:
        self._settings = settings
        self._instruments = instruments
        self._manager = stream_manager or OandaStreamManager(settings, instruments)

    async def persist_backfill(self, session: AsyncSession, symbol: str) -> int:
        gaps = await self._manager.backfill_gaps(symbol)
        if not gaps:
            return 0
        rest = self._manager._rest  # noqa: SLF001
        normalized = await rest.fetch_candles(
            symbol, granularity="M1", count=min(len(gaps) + 2, 500)
        )
        symbol_row = await market_data.get_or_create_symbol(session, symbol)
        return await market_data.upsert_candles(session, symbol_row.id, normalized)

    async def _persist_live_candle(self, session: AsyncSession, candle: LiveCandle) -> None:
        symbol_row = await market_data.get_or_create_symbol(session, candle.symbol)
        normalized = live_candle_to_normalized(candle)
        await market_data.upsert_candles(session, symbol_row.id, [normalized])
        await candle_broadcaster.publish(
            candle.symbol,
            {
                "event": "candle",
                "symbol": candle.symbol,
                "timeframe": normalized.timeframe.value,
                "ts": candle.ts.isoformat(),
                "open": float(candle.open),
                "high": float(candle.high),
                "low": float(candle.low),
                "close": float(candle.close),
                "complete": candle.complete,
            },
        )

    async def run_cycle(
        self,
        session: AsyncSession,
        *,
        max_ticks: int = 200,
    ) -> dict[str, int]:
        """
        Consume up to max_ticks from stream/fallback, persist completed candles,
        and REST-backfill on reconnect.
        """
        ticks_seen = 0
        candles_persisted = 0
        backfill_rows = 0
        was_connected = self._manager.connected

        async for tick in self._manager.ticks_with_fallback():
            if self._manager.connected and not was_connected:
                for instrument in self._instruments:
                    backfill_rows += await self.persist_backfill(session, instrument)

            was_connected = self._manager.connected
            completed, _updated = self._manager.ingest_tick(tick)
            for live in completed:
                await self._persist_live_candle(session, live)
                candles_persisted += 1

            ticks_seen += 1
            if ticks_seen >= max_ticks:
                break

        return {
            "ticks_seen": ticks_seen,
            "candles_persisted": candles_persisted,
            "backfill_rows": backfill_rows,
        }


async def run_market_stream_cycle(
    session: AsyncSession,
    *,
    instruments: list[str] | None = None,
    max_ticks: int = 200,
) -> dict[str, int]:
    from app.core.config import get_settings

    settings = get_settings()
    symbols = instruments or ["EURUSD"]
    consumer = OandaCandleStreamConsumer(settings, symbols)
    return await consumer.run_cycle(session, max_ticks=max_ticks)

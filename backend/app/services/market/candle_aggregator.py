from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PriceTick:
    symbol: str
    bid: Decimal
    ask: Decimal
    ts: datetime


@dataclass
class LiveCandle:
    symbol: str
    timeframe_minutes: int
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    complete: bool = False


def _bucket_start(ts: datetime, timeframe_minutes: int) -> datetime:
    ts = ts.astimezone(UTC)
    minute = (ts.minute // timeframe_minutes) * timeframe_minutes
    return ts.replace(minute=minute, second=0, microsecond=0)


class CandleAggregator:
    """Aggregates pricing ticks into OHLC candles server-side."""

    def __init__(self, *, timeframe_minutes: int = 1) -> None:
        self._timeframe_minutes = timeframe_minutes
        self._active: dict[tuple[str, datetime], LiveCandle] = {}

    @property
    def timeframe_minutes(self) -> int:
        return self._timeframe_minutes

    def ingest_tick(self, tick: PriceTick) -> tuple[LiveCandle | None, LiveCandle | None]:
        """
        Returns (completed_candle, updated_candle).
        Out-of-order ticks for older buckets are ignored.
        """
        mid = (tick.bid + tick.ask) / Decimal("2")
        bucket = _bucket_start(tick.ts, self._timeframe_minutes)
        key = (tick.symbol, bucket)

        existing = self._active.get(key)
        if existing is None:
            candle = LiveCandle(
                symbol=tick.symbol,
                timeframe_minutes=self._timeframe_minutes,
                ts=bucket,
                open=mid,
                high=mid,
                low=mid,
                close=mid,
            )
            self._active[key] = candle
            return None, candle

        if tick.ts < existing.ts:
            return None, None

        existing.high = max(existing.high, mid)
        existing.low = min(existing.low, mid)
        existing.close = mid
        return None, existing

    def close_bucket(self, symbol: str, bucket_ts: datetime) -> LiveCandle | None:
        key = (symbol, bucket_ts)
        candle = self._active.pop(key, None)
        if candle is None:
            return None
        candle.complete = True
        return candle

    def dedupe_ticks(self, ticks: list[PriceTick]) -> list[PriceTick]:
        seen: set[tuple[str, datetime, Decimal, Decimal]] = set()
        unique: list[PriceTick] = []
        for tick in sorted(ticks, key=lambda t: t.ts):
            key = (tick.symbol, tick.ts, tick.bid, tick.ask)
            if key in seen:
                continue
            seen.add(key)
            unique.append(tick)
        return unique


def backfill_missing_ranges(
    *,
    last_ts: datetime,
    now: datetime,
    timeframe_minutes: int,
) -> list[datetime]:
    """Generate missing bucket starts between last_ts and now (exclusive end)."""
    buckets: list[datetime] = []
    cursor = _bucket_start(last_ts + timedelta(minutes=timeframe_minutes), timeframe_minutes)
    end = _bucket_start(now, timeframe_minutes)
    while cursor <= end:
        buckets.append(cursor)
        cursor += timedelta(minutes=timeframe_minutes)
    return buckets

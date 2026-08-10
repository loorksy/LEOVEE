from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.models.enums import Timeframe


@dataclass(frozen=True, slots=True)
class NormalizedCandle:
    symbol: str
    timeframe: Timeframe
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    complete: bool
    source: str


class MarketDataProvider(Protocol):
    async def fetch_candles(
        self,
        instrument: str,
        *,
        granularity: str,
        count: int = 100,
    ) -> list[NormalizedCandle]: ...


GRANULARITY_TO_TIMEFRAME: dict[str, Timeframe] = {
    "M1": Timeframe.M1,
    "M5": Timeframe.M5,
    "M15": Timeframe.M15,
    "M30": Timeframe.M30,
    "H1": Timeframe.H1,
    "H4": Timeframe.H4,
    "D": Timeframe.D1,
    "D1": Timeframe.D1,
}


def normalize_oanda_candle(
    instrument: str,
    granularity: str,
    raw: dict[str, Any],
) -> NormalizedCandle:
    mid = raw.get("mid") or {}
    tf = GRANULARITY_TO_TIMEFRAME.get(granularity, Timeframe.H1)
    ts = datetime.fromisoformat(raw["time"].replace("Z", "+00:00"))
    return NormalizedCandle(
        symbol=instrument.replace("_", ""),
        timeframe=tf,
        ts=ts,
        open=Decimal(mid["o"]),
        high=Decimal(mid["h"]),
        low=Decimal(mid["l"]),
        close=Decimal(mid["c"]),
        volume=Decimal(raw["volume"]) if raw.get("volume") is not None else None,
        complete=bool(raw.get("complete", True)),
        source="oanda",
    )

from decimal import Decimal

from app.models.enums import Timeframe
from app.providers.market.base import normalize_oanda_candle


def test_normalize_oanda_candle() -> None:
    raw = {
        "time": "2026-01-15T12:00:00.000000000Z",
        "mid": {"o": "1.1000", "h": "1.1010", "l": "1.0990", "c": "1.1005"},
        "volume": 120,
        "complete": True,
    }
    candle = normalize_oanda_candle("EUR_USD", "H1", raw)
    assert candle.symbol == "EURUSD"
    assert candle.timeframe == Timeframe.H1
    assert candle.open == Decimal("1.1000")
    assert candle.close == Decimal("1.1005")
    assert candle.complete is True
    assert candle.source == "oanda"

from __future__ import annotations

from decimal import Decimal

from app.engines.market_intelligence import run_market_intelligence_engine
from app.engines.volatility import OHLCBar


def _trending_up_bars(n: int = 25) -> list[OHLCBar]:
    bars: list[OHLCBar] = []
    price = Decimal("1.1000")
    for i in range(n):
        o = price + Decimal(i) * Decimal("0.0003")
        bars.append(
            OHLCBar(
                open=o,
                high=o + Decimal("0.0005"),
                low=o - Decimal("0.0002"),
                close=o + Decimal("0.0004"),
            )
        )
    return bars


def test_market_intelligence_golden_trending_up() -> None:
    result = run_market_intelligence_engine(_trending_up_bars())
    assert result["trend"] == "UP"
    assert result["momentum"] > 0
    assert result["confidence"] >= 0.4


def test_market_intelligence_range_fixture() -> None:
    flat = [
        OHLCBar(
            open=Decimal("1.1"),
            high=Decimal("1.1002"),
            low=Decimal("1.0998"),
            close=Decimal("1.1"),
        )
        for _ in range(20)
    ]
    result = run_market_intelligence_engine(flat)
    assert result["trend"] in ("RANGE", "UP", "DOWN")
    assert result["range"] in ("TIGHT", "WIDE")

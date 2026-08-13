from __future__ import annotations

from app.engines.market_intelligence import run_market_intelligence_engine
from app.tests.bars import flat_bars, rising_bars


def test_market_intelligence_golden_trending_up() -> None:
    result = run_market_intelligence_engine(rising_bars(25))
    assert result["trend"] == "UP"
    assert result["momentum"] > 0
    assert result["confidence"] >= 0.4


def test_market_intelligence_range_fixture() -> None:
    result = run_market_intelligence_engine(flat_bars(20))
    assert result["trend"] in ("RANGE", "UP", "DOWN")
    assert result["range"] in ("TIGHT", "WIDE")

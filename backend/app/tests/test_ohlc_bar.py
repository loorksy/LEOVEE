"""The engine bar type: carries time, computes in float."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.engines.bar import OHLCBar, bar_from_candle, bars_from_candles
from app.tests.bars import EPOCH, rising_bars

pytestmark = pytest.mark.no_db


def _candle(**overrides: object) -> SimpleNamespace:
    base = {
        "ts": datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        "open": Decimal("1.1000"),
        "high": Decimal("1.1020"),
        "low": Decimal("1.0990"),
        "close": Decimal("1.1010"),
        "volume": Decimal("321"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_a_bar_requires_a_timestamp() -> None:
    """Anchors are (ts, price) pairs; a bar without time cannot produce one."""
    with pytest.raises(TypeError):
        OHLCBar(open=1.0, high=1.0, low=1.0, close=1.0)  # type: ignore[call-arg]


def test_candle_conversion_preserves_time_and_drops_decimal() -> None:
    bar = bar_from_candle(_candle())
    assert bar.ts == datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    assert bar.close == 1.1010
    assert isinstance(bar.close, float)
    assert bar.volume == 321.0


def test_missing_volume_becomes_zero_not_an_error() -> None:
    """Not every provider reports forex volume; absence must not break analysis."""
    candle = _candle()
    del candle.volume
    assert bar_from_candle(candle).volume == 0.0


def test_null_volume_becomes_zero() -> None:
    assert bar_from_candle(_candle(volume=None)).volume == 0.0


def test_bars_from_candles_preserves_order() -> None:
    candles = [
        _candle(ts=datetime(2026, 3, 1, hour, tzinfo=UTC), close=Decimal(f"1.10{hour:02d}"))
        for hour in (9, 10, 11)
    ]
    bars = bars_from_candles(candles)
    assert [b.ts.hour for b in bars] == [9, 10, 11]


def test_range_and_direction_helpers() -> None:
    bull = OHLCBar(ts=EPOCH, open=1.0, high=1.5, low=0.9, close=1.2)
    bear = OHLCBar(ts=EPOCH, open=1.2, high=1.5, low=0.9, close=1.0)
    assert bull.range == pytest.approx(0.6)
    assert bull.is_bullish
    assert not bear.is_bullish


def test_bars_are_immutable() -> None:
    """Engines share bar lists; one mutating them would corrupt the others."""
    bar = rising_bars(1)[0]
    with pytest.raises(AttributeError):
        bar.close = 2.0  # type: ignore[misc]


def test_builder_series_are_deterministic() -> None:
    """Fixtures must not read the clock, or golden comparisons drift per run."""
    assert rising_bars(5) == rising_bars(5)
    assert rising_bars(5)[0].ts == EPOCH

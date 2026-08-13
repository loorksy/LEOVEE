from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.engines.decision import run_decision_engine
from app.engines.liquidity import run_liquidity_engine
from app.engines.risk import run_risk_engine
from app.engines.scenario import run_scenario_engine
from app.engines.status import (
    ENGINE_NOT_IMPLEMENTED,
    ENGINE_STATUS,
    EngineStatus,
    is_unavailable,
)
from app.engines.structure import run_structure_engine
from app.engines.volatility import OHLCBar, run_volatility_engine
from app.engines.zones import run_zones_engine
from app.services.learning.calibration import apply_calibration
from app.services.market.candle_aggregator import CandleAggregator, PriceTick


def _bars() -> list[OHLCBar]:
    return [
        OHLCBar(
            open=Decimal("1.1"), high=Decimal("1.2"), low=Decimal("1.0"), close=Decimal("1.15")
        ),
        OHLCBar(
            open=Decimal("1.15"), high=Decimal("1.25"), low=Decimal("1.1"), close=Decimal("1.2")
        ),
    ]


def test_volatility_engine_is_implemented() -> None:
    """ATR is genuine arithmetic over the bars, not a placeholder."""
    vol = run_volatility_engine(_bars())
    assert vol["regime"]
    assert not is_unavailable(vol)


@pytest.mark.parametrize(
    ("name", "run"),
    [
        ("structure", lambda: run_structure_engine(_bars())),
        ("liquidity", lambda: run_liquidity_engine(_bars())),
        ("zones", lambda: run_zones_engine(_bars())),
        ("scenarios", lambda: run_scenario_engine({}, {}, {})),
    ],
)
def test_placeholder_engines_report_unavailable_rather_than_inventing(
    name: str, run: Callable[[], dict[str, object]]
) -> None:
    """Until M4 these must decline to answer, not fabricate evidence.

    The earlier stubs returned confident-looking output — a supply and a demand
    zone at a hardcoded strength of 0.5, scenario confidences picked by hand —
    which reached the user as measured evidence. A missing answer is recoverable;
    an invented one is not detectable.
    """
    output = run()
    assert is_unavailable(output), f"{name} still returns a fabricated answer: {output}"
    assert output["reason"] == ENGINE_NOT_IMPLEMENTED
    assert ENGINE_STATUS[name] is EngineStatus.PLACEHOLDER


def test_decision_engine_fails_closed_without_scenarios() -> None:
    """A missing input must degrade the decision, never raise out of the pipeline."""
    risk = run_risk_engine(entry=Decimal("1.2"), stop=Decimal("1.18"))
    decision = run_decision_engine({"status": "unavailable"}, risk)
    assert decision["direction"] == "NO_TRADE"
    assert decision["confidence"] is None


def test_decision_engine_maps_scenarios_when_they_exist() -> None:
    risk = run_risk_engine(entry=Decimal("1.2"), stop=Decimal("1.18"))
    scenarios = {
        "scenarios": [
            {"label": "BULLISH", "confidence": 0.7},
            {"label": "BEARISH", "confidence": 0.2},
        ]
    }
    decision = run_decision_engine(scenarios, risk)
    assert decision["direction"] == "BUY"


def test_calibration_never_returns_raw_only() -> None:
    adjusted = apply_calibration(Decimal("0.9"), predicted_count=50, realized_success_count=10)
    assert adjusted < Decimal("0.9")


def test_candle_aggregator_dedupes_and_orders_ticks() -> None:
    agg = CandleAggregator(timeframe_minutes=1)
    ts = datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC)
    ticks = [
        PriceTick("EURUSD", Decimal("1.1"), Decimal("1.1002"), ts),
        PriceTick("EURUSD", Decimal("1.1"), Decimal("1.1002"), ts),
        PriceTick("EURUSD", Decimal("1.1001"), Decimal("1.1003"), ts),
    ]
    ordered = agg.dedupe_ticks(ticks)
    assert len(ordered) == 2
    completed, updated = agg.ingest_tick(ordered[0])
    assert not completed
    assert updated is not None
    assert updated.close == Decimal("1.1001")

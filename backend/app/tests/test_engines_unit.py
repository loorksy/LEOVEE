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
from app.tests.bars import flat_bars, rising_bars, swinging_bars


def _bars() -> list[OHLCBar]:
    return rising_bars(20)


def test_volatility_engine_is_implemented() -> None:
    """ATR is genuine arithmetic over the bars, not a placeholder."""
    vol = run_volatility_engine(_bars())
    assert vol["regime"]
    assert not is_unavailable(vol)


@pytest.mark.parametrize(
    ("name", "run"),
    [
        ("structure", lambda: run_structure_engine(swinging_bars(20))),
        ("liquidity", lambda: run_liquidity_engine(swinging_bars(20))),
        ("zones", lambda: run_zones_engine(swinging_bars(20))),
    ],
)
def test_evidence_engines_answer_on_a_real_series(
    name: str, run: Callable[[], dict[str, object]]
) -> None:
    """Ported in M4 — these no longer abstain, and no longer fabricate."""
    output = run()
    assert not is_unavailable(output), f"{name} declined on a well-formed series"
    assert ENGINE_STATUS[name] is EngineStatus.IMPLEMENTED


@pytest.mark.parametrize(
    ("name", "run"),
    [
        ("structure", lambda: run_structure_engine(rising_bars(10))),
        ("liquidity", lambda: run_liquidity_engine(rising_bars(10))),
        ("zones", lambda: run_zones_engine(rising_bars(10))),
    ],
)
def test_evidence_engines_abstain_below_the_minimum_window(
    name: str, run: Callable[[], dict[str, object]]
) -> None:
    """Too few bars is a real condition on a 1-minute chart at the open.

    Abstaining is the honest answer; a bias derived from ten bars is noise
    wearing a label.
    """
    output = run()
    assert is_unavailable(output), f"{name} answered on a 10-bar series"
    assert output["reason"] == ENGINE_NOT_IMPLEMENTED or output["status"] == "unavailable"


def test_zones_are_not_fabricated_from_the_last_bar() -> None:
    """The placeholder returned a demand and a supply zone for any input.

    A flat series has no imbalance, so a correct engine reports none rather
    than manufacturing a pair around the final candle.
    """
    output = run_zones_engine(flat_bars(120))
    if not is_unavailable(output):
        assert output["zones"] == []


def test_scenarios_derive_confidence_from_evidence_not_constants() -> None:
    """The placeholder emitted 0.55 / 0.35 regardless of the market."""
    bars = swinging_bars(20)
    structure = run_structure_engine(bars)
    volatility = run_volatility_engine(bars)
    liquidity = run_liquidity_engine(bars)
    zones = run_zones_engine(bars)
    result = run_scenario_engine(structure, volatility, liquidity, zones)
    assert not is_unavailable(result)

    labels = [s["label"] for s in result["scenarios"]]
    # ADR 0002: two directional scenarios and an invalidation, never an
    # abstention scenario.
    assert labels == ["BULLISH", "BEARISH"]
    assert "NO_TRADE" not in labels
    assert result["invalidation"]["condition"] in ("CLOSE_BELOW", "CLOSE_ABOVE")

    confidences = [s["confidence"] for s in result["scenarios"]]
    assert all(0.0 < c < 1.0 for c in confidences)
    # Nothing can be certain: the evidence set is finite and every input is a
    # heuristic over a bounded window.
    assert max(confidences) <= 0.85


def test_scenarios_follow_the_structural_bias() -> None:
    up = swinging_bars(20, drift=4.0)
    down = swinging_bars(20, drift=-4.0)

    def leading(bars: list[OHLCBar]) -> str:
        structure = run_structure_engine(bars)
        result = run_scenario_engine(
            structure,
            run_volatility_engine(bars),
            run_liquidity_engine(bars),
            run_zones_engine(bars),
        )
        best = max(result["scenarios"], key=lambda s: s["confidence"])
        return str(best["label"])

    assert leading(up) == "BULLISH"
    assert leading(down) == "BEARISH"


def test_decision_engine_fails_closed_without_scenarios() -> None:
    """A missing input must degrade the decision, never raise out of the pipeline."""
    risk = run_risk_engine(entry=Decimal("2000.00"), stop=Decimal("1996.00"))
    decision = run_decision_engine({"status": "unavailable"}, risk)
    assert decision["direction"] == "NO_TRADE"
    assert decision["confidence"] is None


def test_decision_engine_maps_scenarios_when_they_exist() -> None:
    risk = run_risk_engine(entry=Decimal("2000.00"), stop=Decimal("1996.00"))
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
        PriceTick("XAUUSD", Decimal("1.1"), Decimal("1.1002"), ts),
        PriceTick("XAUUSD", Decimal("1.1"), Decimal("1.1002"), ts),
        PriceTick("XAUUSD", Decimal("1.1001"), Decimal("1.1003"), ts),
    ]
    ordered = agg.dedupe_ticks(ticks)
    assert len(ordered) == 2
    completed, updated = agg.ingest_tick(ordered[0])
    assert not completed
    assert updated is not None
    assert updated.close == Decimal("1.1001")

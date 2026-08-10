from datetime import UTC, datetime
from decimal import Decimal

from app.engines.decision import run_decision_engine
from app.engines.liquidity import run_liquidity_engine
from app.engines.risk import run_risk_engine
from app.engines.scenario import run_scenario_engine
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


def test_volatility_and_structure_engines() -> None:
    bars = _bars()
    vol = run_volatility_engine(bars)
    structure = run_structure_engine(bars)
    assert vol["regime"]
    assert structure["bias"]


def test_liquidity_zones_scenario_decision_chain() -> None:
    bars = _bars()
    structure = run_structure_engine(bars)
    vol = run_volatility_engine(bars)
    liquidity = run_liquidity_engine(bars)
    zones = run_zones_engine(bars)
    scenarios = run_scenario_engine(structure, vol, liquidity)
    risk = run_risk_engine(entry=Decimal("1.2"), stop=Decimal("1.18"))
    decision = run_decision_engine(scenarios, risk)
    assert zones["zones"]
    assert decision["direction"] in {"BUY", "SELL", "WAIT", "NO_TRADE"}


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

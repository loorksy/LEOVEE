"""Every engine's real output must validate against its declared contract.

`schemas/engines.py` was frozen before the engines were written, deliberately:
it is the interface the decision stage, the recommendation lifecycle and the
chart all bind to. The cost of freezing it first is that nothing forces it to
stay true — and it did not. `PlanSanityOutput` went on requiring a `spread`
object with a trading session and a `source: "observed" | "static_model"`
provenance flag for a whole phase after ADR 0010 deleted the cost model that
produced it. The declared contract described an engine that no longer existed,
and no test noticed, because the parser it feeds is not wired in yet.

This runs each engine on real bars and validates what actually comes back. A
contract that has drifted from its engine fails here rather than at the moment
something first tries to parse it in production.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.engines.bar import OHLCBar
from app.engines.geometry import run_geometry_engine
from app.engines.liquidity import run_liquidity_engine
from app.engines.market_intelligence import run_market_intelligence_engine
from app.engines.mtf import run_mtf_engine
from app.engines.plan_sanity import measure_price_context, run_plan_sanity_engine
from app.engines.primitives.pivots import geometry_atr
from app.engines.risk import run_risk_engine
from app.engines.scenario import run_scenario_engine
from app.engines.structure import run_structure_engine
from app.engines.volatility import run_volatility_engine
from app.engines.zones import run_zones_engine
from app.schemas.engines import EngineName, EngineUnavailable, parse_engine_output
from app.tests.bars import swinging_bars

pytestmark = pytest.mark.no_db


def _bars() -> list[OHLCBar]:
    """A tape every engine can read, so a decline does not stand in for a pass."""
    return swinging_bars(30, start=2000.0, drift=3.0, swing=9.0, bars_per_leg=4)


def _outputs() -> dict[EngineName, dict[str, Any]]:
    bars = _bars()
    atr = geometry_atr(bars)
    structure = run_structure_engine(bars)
    volatility = run_volatility_engine(bars)
    liquidity = run_liquidity_engine(bars)
    zones = run_zones_engine(bars)
    mtf = run_mtf_engine({"M15": bars})
    entry = bars[-1].close
    return {
        EngineName.VOLATILITY: volatility,
        EngineName.STRUCTURE: structure,
        EngineName.GEOMETRY: run_geometry_engine(bars),
        EngineName.LIQUIDITY: liquidity,
        EngineName.ZONES: zones,
        EngineName.SCENARIOS: run_scenario_engine(structure, volatility, liquidity, zones, mtf),
        EngineName.MARKET_INTELLIGENCE: run_market_intelligence_engine(bars),
        EngineName.MTF: mtf,
        EngineName.RISK: run_risk_engine(
            entry=Decimal(str(entry)),
            stop=Decimal(str(entry - atr)),
            targets=[Decimal(str(entry + atr * 2))],
        ),
        EngineName.PLAN_SANITY: run_plan_sanity_engine(
            entry=entry,
            stop=entry - atr,
            targets=[entry + atr * 2],
            context=measure_price_context(bars, atr=atr),
        ),
    }


@pytest.mark.parametrize("engine", list(EngineName), ids=lambda e: e.value)
def test_each_engine_output_matches_its_declared_contract(engine: EngineName) -> None:
    payload = _outputs()[engine]
    parsed = parse_engine_output(engine, payload)
    # A decline validating is not the contract being satisfied — it is the
    # engine having nothing to say, which would let a stale contract pass
    # forever on a fixture the engine cannot read.
    assert not isinstance(parsed, EngineUnavailable), payload


def test_every_engine_has_a_registered_contract() -> None:
    """A new engine without one raises only when something first parses it."""
    for engine in EngineName:
        parse_engine_output(
            engine,
            {
                "status": "unavailable",
                "engine": engine.value,
                "reason": "INSUFFICIENT_DATA",
            },
        )

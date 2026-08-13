"""The typed contracts: what an engine and a decision are allowed to say.

These are frozen before M6/M7/M9 consume them, so the tests are the record of
what the contract promises rather than a description of what the consumers
happened to accept.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.engines.status import ENGINE_STATUS, engine_unavailable
from app.models.enums import RecommendationDirection
from app.schemas.decision import (
    ANALYTICAL_DIRECTIONS,
    DecisionOutput,
    DegradedReason,
    ExecutionState,
    PlanLevels,
    PlanType,
)
from app.schemas.engines import (
    EngineName,
    EngineUnavailable,
    MarketIntelligenceOutput,
    UnavailableReason,
    parse_engine_output,
)

pytestmark = pytest.mark.no_db


def _buy(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "direction": RecommendationDirection.BUY,
        "confidence": 0.72,
        "plan_type": PlanType.IMMEDIATE,
        "execution_state": ExecutionState.VALID_NOW,
        "levels": {"entry": 2000.0, "stop": 1996.0, "targets": [2008.0, 2014.0]},
    }
    return {**base, **overrides}


# --- the decision contract ---------------------------------------------------


def test_a_completed_analysis_carries_a_direction_and_a_full_plan() -> None:
    decision = DecisionOutput.model_validate(_buy())
    assert decision.direction in ANALYTICAL_DIRECTIONS
    assert decision.degraded is False


def test_no_trade_must_name_the_failure_that_produced_it() -> None:
    """NO_TRADE is an operational failure, never an opinion (ADR 0002)."""
    with pytest.raises(ValidationError, match="must name its reason"):
        DecisionOutput.model_validate({"direction": RecommendationDirection.NO_TRADE})

    ok = DecisionOutput.model_validate(
        {
            "direction": RecommendationDirection.NO_TRADE,
            "degraded": True,
            "degraded_reason": DegradedReason.ENGINE_UNAVAILABLE,
            "detail": "geometry",
        }
    )
    assert ok.confidence is None


def test_a_failed_analysis_has_no_confidence_to_report() -> None:
    """A confidence figure on a failure reads as a weak opinion. It is not one."""
    with pytest.raises(ValidationError, match="no confidence"):
        DecisionOutput.model_validate(
            {
                "direction": RecommendationDirection.NO_TRADE,
                "degraded": True,
                "degraded_reason": DegradedReason.LLM_UNAVAILABLE,
                "confidence": 0.3,
            }
        )


def test_a_degraded_run_cannot_also_publish_a_direction() -> None:
    """The fail-closed path and the analytical path must not blur together."""
    with pytest.raises(ValidationError, match="fail closed"):
        DecisionOutput.model_validate(
            _buy(degraded=True, degraded_reason=DegradedReason.STALE_DATA)
        )


def test_wait_is_not_an_analytical_outcome() -> None:
    with pytest.raises(ValidationError, match="not an analytical outcome"):
        DecisionOutput.model_validate({"direction": RecommendationDirection.WAIT})


@pytest.mark.parametrize("missing", ["confidence", "levels", "plan_type", "execution_state"])
def test_a_direction_travels_with_its_whole_plan(missing: str) -> None:
    payload = _buy()
    payload[missing] = None
    with pytest.raises(ValidationError):
        DecisionOutput.model_validate(payload)


def test_a_target_on_the_wrong_side_of_entry_is_rejected() -> None:
    """A sign error here reads downstream as a very confident bad trade."""
    with pytest.raises(ValidationError, match="above entry"):
        PlanLevels(entry=2000.0, stop=1996.0, targets=[1990.0])
    with pytest.raises(ValidationError, match="below entry"):
        PlanLevels(entry=2000.0, stop=2004.0, targets=[2010.0])
    with pytest.raises(ValidationError, match="same price"):
        PlanLevels(entry=2000.0, stop=2000.0, targets=[2010.0])


def test_the_three_axes_stay_separate() -> None:
    """A conditional plan awaiting its trigger is a BUY, not a weak BUY."""
    decision = DecisionOutput.model_validate(
        _buy(
            plan_type=PlanType.CONDITIONAL,
            execution_state=ExecutionState.AWAITING_ACTIVATION,
        )
    )
    assert decision.direction is RecommendationDirection.BUY
    assert decision.confidence == 0.72


# --- the engine contract -----------------------------------------------------


def test_an_unavailable_payload_is_never_coerced_into_a_success_shape() -> None:
    """That coercion is how a missing answer becomes a zeroed one."""
    parsed = parse_engine_output(
        EngineName.MARKET_INTELLIGENCE, engine_unavailable("market_intelligence")
    )
    assert isinstance(parsed, EngineUnavailable)
    assert parsed.reason is UnavailableReason.ENGINE_NOT_IMPLEMENTED


def test_a_real_payload_validates_against_its_engine_model() -> None:
    from app.engines.market_intelligence import run_market_intelligence_engine
    from app.tests.bars import swinging_bars

    payload = run_market_intelligence_engine(
        swinging_bars(14, drift=6.0, swing=9.0, bars_per_leg=5)
    )
    parsed = parse_engine_output(EngineName.MARKET_INTELLIGENCE, payload)
    assert isinstance(parsed, MarketIntelligenceOutput)
    assert parsed.regime == "trending"


def test_every_pipeline_engine_has_a_name_in_the_contract() -> None:
    """The ledger and the contract must not drift apart."""
    contract_names = {name.value for name in EngineName}
    assert set(ENGINE_STATUS) <= contract_names, (
        "an engine runs in the pipeline with no name in schemas/engines.py"
    )


def test_both_unavailable_reasons_are_expressible() -> None:
    """Unported and short-of-data are different facts and stay different."""
    assert {r.value for r in UnavailableReason} == {
        "ENGINE_NOT_IMPLEMENTED",
        "INSUFFICIENT_DATA",
    }

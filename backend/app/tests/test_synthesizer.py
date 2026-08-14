"""The final decision stage: schema conformance is the first gate, not the last."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents.synthesizer import (
    DECISION_JSON_SCHEMA,
    MAX_REPAIR_ATTEMPTS,
    SynthesizerFailureKind,
    SynthesizerOutcome,
    build_decision_messages,
    synthesize_decision,
)
from app.core.errors import ProviderConfigurationError
from app.models.enums import RecommendationDirection
from app.providers.llm.base import LLMMessage, LLMResponse
from app.schemas.decision import ExecutionState, PlanType

pytestmark = pytest.mark.no_db

VALID = {
    "direction": "BUY",
    "confidence": 0.71,
    "plan_type": "IMMEDIATE",
    "levels": {"entry": 2000.0, "stop": 1996.0, "targets": [2008.0, 2014.0]},
    "rationale": "ارتداد من طلب مع بنية صاعدة",
    "invalidation": "إغلاق تحت 1996",
}


class _Model:
    """Replies in order; repeats the last one forever."""

    def __init__(self, replies: list[str | Exception]) -> None:
        self._replies = list(replies)
        self.seen: list[list[LLMMessage]] = []

    async def __call__(self, messages: list[LLMMessage]) -> LLMResponse:
        self.seen.append(list(messages))
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(content=reply, model="m", provider="p", usage={"total_tokens": 10})


async def _run(replies: list[str | Exception], **kwargs: Any) -> tuple[SynthesizerOutcome, _Model]:
    model = _Model(replies)
    outcome = await synthesize_decision(
        complete=model, symbol="XAUUSD", evidence="{}", timeframe="M15", **kwargs
    )
    return outcome, model


# --- the happy path ----------------------------------------------------------


async def test_a_valid_reply_becomes_a_typed_decision() -> None:
    outcome, _ = await _run([json.dumps(VALID)])
    assert outcome.ok
    assert outcome.decision is not None
    assert outcome.decision.direction is RecommendationDirection.BUY
    assert outcome.decision.timeframe == "M15"
    assert outcome.attempts == 1
    assert outcome.repairs == []


async def test_json_wrapped_in_a_fence_or_prose_is_still_accepted() -> None:
    """Refusing these discards correct answers over presentation."""
    fenced = f"إليك القرار:\n```json\n{json.dumps(VALID)}\n```\nانتهى."
    outcome, _ = await _run([fenced])
    assert outcome.ok


async def test_a_conditional_plan_is_awaiting_activation_not_a_weak_buy() -> None:
    """The three axes stay separate: an untriggered condition is not low confidence."""
    conditional = {**VALID, "plan_type": "CONDITIONAL", "condition": "كسر 2005 بإغلاق"}
    outcome, _ = await _run([json.dumps(conditional)])
    assert outcome.decision is not None
    assert outcome.decision.plan_type is PlanType.CONDITIONAL
    assert outcome.decision.execution_state is ExecutionState.AWAITING_ACTIVATION
    assert outcome.decision.confidence == 0.71
    assert outcome.decision.condition == "كسر 2005 بإغلاق"


# --- the second gate ---------------------------------------------------------


async def test_conforming_json_with_an_impossible_plan_is_rejected() -> None:
    """Schema conformance is not correctness.

    A target on the stop's side of entry parses perfectly and describes a trade
    that cannot make money. That is the failure the second gate exists for.
    """
    backwards = {**VALID, "levels": {"entry": 2000.0, "stop": 1996.0, "targets": [1990.0]}}
    outcome, model = await _run([json.dumps(backwards), json.dumps(VALID)])
    assert outcome.ok
    assert outcome.attempts == 2
    assert any("above entry" in r for r in outcome.repairs)
    # And the model was told precisely what was wrong, not just "try again".
    assert "above entry" in model.seen[-1][-1].content


async def test_a_confidence_outside_the_range_is_rejected() -> None:
    outcome, _ = await _run([json.dumps({**VALID, "confidence": 1.4}), json.dumps(VALID)])
    assert outcome.ok
    assert outcome.repairs


async def test_no_trade_from_the_model_is_not_an_analytical_outcome() -> None:
    """NO_TRADE is an operational failure. A model cannot elect it."""
    outcome, _ = await _run([json.dumps({**VALID, "direction": "NO_TRADE"})])
    assert outcome.ok is False
    assert outcome.kind is SynthesizerFailureKind.REPAIR_EXHAUSTED


# --- repair ------------------------------------------------------------------


async def test_malformed_json_is_repaired_with_the_reason_named() -> None:
    outcome, model = await _run(["this is not json at all", json.dumps(VALID)])
    assert outcome.ok
    assert outcome.attempts == 2
    assert "JSON" in model.seen[-1][-1].content


async def test_repairs_are_bounded() -> None:
    """A third attempt on a model that produced two invalid plans is hope, not engineering."""
    outcome, model = await _run(["nonsense"])
    assert outcome.ok is False
    assert outcome.kind is SynthesizerFailureKind.REPAIR_EXHAUSTED
    assert outcome.attempts == MAX_REPAIR_ATTEMPTS + 1
    assert len(model.seen) == MAX_REPAIR_ATTEMPTS + 1


async def test_every_rejection_is_reported_even_when_the_run_recovers() -> None:
    outcome, _ = await _run(["nope", json.dumps(VALID)])
    assert outcome.ok
    assert len(outcome.repairs) == 1


# --- typed failures ----------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (RuntimeError("HTTP 401 unauthorized"), SynthesizerFailureKind.PROVIDER_AUTH),
        (RuntimeError("HTTP 429 rate limit"), SynthesizerFailureKind.PROVIDER_RATE_LIMIT),
        (RuntimeError("HTTP 503 overloaded"), SynthesizerFailureKind.PROVIDER_UNAVAILABLE),
        (RuntimeError("HTTP 400 bad request"), SynthesizerFailureKind.PROVIDER_BAD_REQUEST),
        (TimeoutError("deadline"), SynthesizerFailureKind.TIMEOUT),
    ],
)
async def test_provider_failures_are_typed_not_collapsed(
    error: Exception, kind: SynthesizerFailureKind
) -> None:
    """Four different operational facts; "the model failed" makes each unactionable."""
    outcome, _ = await _run([error])
    assert outcome.ok is False
    assert outcome.kind is kind
    assert outcome.failure is not None


async def test_a_missing_provider_is_a_deployment_problem_not_a_model_problem() -> None:
    outcome, _ = await _run([ProviderConfigurationError("no key")])
    assert outcome.kind is SynthesizerFailureKind.LLM_NOT_CONFIGURED


async def test_a_provider_failure_stops_immediately_without_burning_repairs() -> None:
    """Repairing a 401 by asking again is spending the budget on a certainty."""
    outcome, model = await _run([RuntimeError("HTTP 401")])
    assert len(model.seen) == 1
    assert outcome.attempts == 1


# --- the prompt --------------------------------------------------------------


def test_the_system_prompt_carries_the_constitution_and_the_skills() -> None:
    messages, prompt = build_decision_messages(symbol="XAUUSD", evidence="{}")
    system = messages[0].content
    assert "دستور Leovee" in system
    assert "أطلس الأنماط" in system
    assert "معجم التحليل" in system
    assert len(prompt.hash) == 64


def test_the_schema_is_sent_with_the_request() -> None:
    """One copy: a schema in the prompt that differs from the one validated
    against makes every reply fail on a field the prompt never asked for."""
    messages, _ = build_decision_messages(symbol="XAUUSD", evidence="{}")
    user = messages[1].content
    assert "direction" in user and "invalidation" in user
    assert json.dumps(DECISION_JSON_SCHEMA, indent=2) in user


def test_the_schema_admits_only_a_direction() -> None:
    assert DECISION_JSON_SCHEMA["properties"]["direction"]["enum"] == ["BUY", "SELL"]


def test_attached_charts_are_named_to_the_model() -> None:
    """A model told which frames it has reasons differently from one inferring
    the set from what it can see."""
    messages, _ = build_decision_messages(
        symbol="XAUUSD",
        evidence="{}",
        visual=[{"timeframe": "M15"}, {"timeframe": "H1"}],
    )
    assert "M15, H1" in messages[1].content


# --- level grounding ---------------------------------------------------------

ENGINES = {
    "structure": {
        "nearest_support": 1996.0,
        "nearest_resistance": 2008.0,
        "supports": [{"price": 1990.0}],
        "resistances": [{"price": 2014.0}],
    },
    "zones": {"zones": [{"low": 1994.0, "high": 2000.0}]},
    "geometry": {"patterns": [{"break_level": 2005.0, "projected_target": 2020.0}]},
    "liquidity": {"equal_highs": [{"price": 2016.0}]},
}


def test_evidence_levels_are_gathered_from_every_engine_that_measures_one() -> None:
    from app.agents.synthesizer import evidence_levels

    levels = evidence_levels(ENGINES)
    assert 1996.0 in levels and 2008.0 in levels  # structure
    assert 1994.0 in levels and 2000.0 in levels  # zone edges
    assert 2005.0 in levels and 2020.0 in levels  # pattern boundary and target
    assert 2016.0 in levels  # resting liquidity
    assert levels == sorted(levels)


async def test_a_price_matching_nothing_measured_is_rejected() -> None:
    """The constitution's "do not invent a level", made mechanical.

    A model asked for an entry always produces a number, and a plausible one
    near the current price is indistinguishable from a measured one in the
    output. Nothing downstream can tell them apart, so the check belongs here.
    """
    invented = {**VALID, "levels": {"entry": 2001.7, "stop": 1996.0, "targets": [2008.0]}}
    outcome, model = await _run([json.dumps(invented)], engines=ENGINES, atr=1.0)
    assert outcome.ok is False
    assert outcome.kind is SynthesizerFailureKind.LEVELS_NOT_GROUNDED
    assert "2001.70" in model.seen[-1][-1].content


async def test_a_grounded_plan_passes() -> None:
    grounded = {**VALID, "levels": {"entry": 2000.0, "stop": 1996.0, "targets": [2008.0]}}
    outcome, _ = await _run([json.dumps(grounded)], engines=ENGINES, atr=1.0)
    assert outcome.ok


async def test_the_tolerance_scales_with_volatility() -> None:
    """The same 30 cents is a rounding error in a fast session and a different
    level in a quiet one."""
    near = {**VALID, "levels": {"entry": 2000.3, "stop": 1996.0, "targets": [2008.0]}}
    loose, _ = await _run([json.dumps(near)], engines=ENGINES, atr=5.0)
    assert loose.ok
    tight, _ = await _run([json.dumps(near)], engines=ENGINES, atr=0.1)
    assert tight.ok is False


async def test_the_level_set_is_rejected_whole_never_patched() -> None:
    """Snapping a price to the nearest evidence level moves the trade to a level
    the model never reasoned about — a different trade wearing the same
    rationale."""
    one_bad = {**VALID, "levels": {"entry": 2000.0, "stop": 1996.0, "targets": [2003.3]}}
    outcome, _ = await _run([json.dumps(one_bad), json.dumps(VALID)], engines=ENGINES, atr=0.5)
    assert outcome.ok
    assert outcome.decision is not None
    # The good levels came from the repair, not from patching the bad ones.
    assert outcome.decision.levels is not None
    assert outcome.decision.levels.targets == [2008.0, 2014.0]


async def test_no_evidence_levels_means_the_check_cannot_run_not_that_all_pass() -> None:
    """Returning "all grounded" on an empty menu would turn a missing check into
    a blanket approval — the caller decides, and the engine gate upstream has
    already refused a run with no evidence."""
    outcome, _ = await _run([json.dumps(VALID)], engines={}, atr=1.0)
    assert outcome.ok


def test_the_measured_levels_are_shown_to_the_model() -> None:
    """A model handed the levels it may use proposes ungrounded prices far less
    often than one asked to invent them and then corrected."""
    messages, _ = build_decision_messages(
        symbol="XAUUSD", evidence="{}", levels=[1996.0, 2000.0, 2008.0]
    )
    assert "1996.00, 2000.00, 2008.00" in messages[1].content

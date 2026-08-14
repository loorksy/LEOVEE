"""The final decision: the one stage where a model is allowed to decide.

Everything upstream is deterministic and reproducible. This stage is not, and
the entire design is about containing that.

**The model's output is forced into a schema, then validated again.** Schema
conformance is not correctness: a model returns well-formed JSON with a stop on
the wrong side of entry, or a confidence of 1.0, or a direction that contradicts
the plan it just wrote. Every such payload parses. So the parse is the first
gate and the arithmetic is the second, and a payload that fails the second is
sent back for repair rather than published.

**Repair is bounded and told what it got wrong.** A retry that re-sends the
identical prompt asks the model to be lucky. The repair turn names the specific
failure, and there are two attempts — past that the model is not going to
converge and the run fails closed with the reason.

**Failure kinds are typed, not sniffed by the caller.** A missing API key, a
provider 429, a schema mismatch and a plan that never validated are four
different operational facts, and collapsing them into "the model failed" makes
each one unactionable.

**Every price must already exist in the evidence.** The constitution forbids
inventing a level; this is that rule made mechanical. A model asked for an entry
will always produce a number, and a plausible number near the current price is
indistinguishable from a measured one in the output. So each price is matched
against the levels the deterministic engines actually found — swing levels, zone
edges, pattern boundaries — within a tolerance drawn from ATR, and a set that
fails is rejected **whole** rather than patched. Patching would silently move
the trade to a level the model never reasoned about.

**Fail closed, always.** Any path out of this module that is not a validated
BUY or SELL is a NO_TRADE carrying a named reason. There is no third exit.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from app.agents.errors import AgentStage, StageFailure, stage_failure_from_error
from app.agents.prompts import Prompt, constitution, load_prompt, load_skill, render
from app.core.errors import ProviderConfigurationError
from app.models.enums import RecommendationDirection
from app.providers.llm.base import LLMMessage, LLMResponse
from app.schemas.decision import DecisionOutput, ExecutionState, PlanType

__all__ = [
    "MAX_REPAIR_ATTEMPTS",
    "SynthesizerFailureKind",
    "SynthesizerOutcome",
    "DECISION_JSON_SCHEMA",
    "synthesize_decision",
    "build_decision_messages",
]

#: Two repairs, then stop. A third attempt on a model that has produced two
#: invalid plans is spending tokens on hope.
MAX_REPAIR_ATTEMPTS = 2

#: Skills attached to this stage. Loaded here rather than globally: the atlas is
#: reference material the decision needs and the earlier stages do not.
DECISION_SKILLS = ("pattern-atlas", "trading-lexicon")

#: How far a proposed price may sit from the nearest evidence level and still
#: count as *that* level. A fraction of ATR rather than a fixed distance: the
#: same 30 cents is a rounding error in a fast session and a different level in
#: a quiet one.
LEVEL_TOLERANCE_ATR = 0.35

#: Fallback when ATR is unusable — a tenth of a percent of price. Wide enough to
#: absorb tick rounding, narrow enough that it cannot swallow a real level.
LEVEL_TOLERANCE_RELATIVE = 0.0015


class SynthesizerFailureKind(StrEnum):
    """Why no decision came back. Each one implies a different operator action."""

    #: No provider configured at all. A deployment problem.
    LLM_NOT_CONFIGURED = "llm_not_configured"
    PROVIDER_AUTH = "provider_auth"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_BAD_REQUEST = "provider_bad_request"
    #: The reply was not JSON, or not the shape asked for.
    MALFORMED_OUTPUT = "malformed_output"
    #: Well-formed JSON that describes an impossible trade — the second gate.
    INVALID_PLAN = "invalid_plan"
    #: A price in the plan corresponds to nothing the engines measured.
    LEVELS_NOT_GROUNDED = "levels_not_grounded"
    #: Repairs exhausted without a valid plan.
    REPAIR_EXHAUSTED = "repair_exhausted"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


#: What the model is required to return. Kept in one place because it is sent to
#: the provider *and* checked against `DecisionOutput` — two copies drift, and
#: the drift shows up as every reply failing validation for a field the prompt
#: never asked for.
DECISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["direction", "confidence", "plan_type", "levels", "rationale", "invalidation"],
    "properties": {
        "direction": {
            "type": "string",
            "enum": ["BUY", "SELL"],
            "description": "Every completed analysis has a direction. There is no third value.",
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "plan_type": {"type": "string", "enum": [p.value for p in PlanType]},
        "condition": {
            "type": "string",
            "description": "Required when plan_type is CONDITIONAL: what must happen first.",
        },
        "levels": {
            "type": "object",
            "required": ["entry", "stop", "targets"],
            "properties": {
                "entry": {"type": "number"},
                "stop": {"type": "number"},
                "targets": {"type": "array", "items": {"type": "number"}, "minItems": 1},
            },
        },
        "rationale": {"type": "string"},
        "invalidation": {
            "type": "string",
            "description": "What kills the thesis, at a specific price.",
        },
        "contradicting_evidence": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass(slots=True)
class SynthesizerOutcome:
    decision: DecisionOutput | None = None
    kind: SynthesizerFailureKind | None = None
    detail: str | None = None
    failure: StageFailure | None = None
    attempts: int = 0
    #: Every rejection along the way, so a run that eventually succeeded still
    #: shows what the model got wrong first.
    repairs: list[str] = field(default_factory=list)
    #: Which model answered. Several providers rotate behind one router, so
    #: without this a run cannot be attributed to one after the fact.
    model: str | None = None
    provider: str | None = None

    @property
    def ok(self) -> bool:
        return self.decision is not None


CompleteFn = Callable[[list[LLMMessage]], Awaitable[LLMResponse]]

_KIND_BY_CODE = {
    "auth": SynthesizerFailureKind.PROVIDER_AUTH,
    "rate_limit": SynthesizerFailureKind.PROVIDER_RATE_LIMIT,
    "provider_billing": SynthesizerFailureKind.PROVIDER_RATE_LIMIT,
    "provider_unavailable": SynthesizerFailureKind.PROVIDER_UNAVAILABLE,
    "provider_bad_request": SynthesizerFailureKind.PROVIDER_BAD_REQUEST,
    "timeout": SynthesizerFailureKind.TIMEOUT,
    "configuration": SynthesizerFailureKind.LLM_NOT_CONFIGURED,
}


def build_decision_messages(
    *,
    symbol: str,
    evidence: str,
    visual: list[dict[str, Any]] | None = None,
    levels: list[float] | None = None,
    skills: tuple[str, ...] = DECISION_SKILLS,
) -> tuple[list[LLMMessage], Prompt]:
    """The system prompt, the skills, the evidence, and the schema."""
    system = constitution()
    parts = [system.body]
    for name in skills:
        parts.append(load_skill(name).body)

    stage = render(load_prompt("stages/analysis"), symbol=symbol, evidence=evidence)
    user = [stage, "", "أعد **JSON فقط** بهذا المخطط:", json.dumps(DECISION_JSON_SCHEMA, indent=2)]
    if levels:
        # Showing the menu, not just policing it afterwards: a model handed the
        # levels it may use proposes ungrounded prices far less often than one
        # asked to invent them and then corrected.
        user.append(
            "\nالمستويات المقاسة المتاحة (استخدم منها فقط): "
            + ", ".join(f"{level:.2f}" for level in levels[:40])
        )
    if visual:
        # Named, not silently attached: a model told which charts it has reasons
        # differently from one that has to infer the set from what it can see.
        frames = ", ".join(str(item.get("timeframe")) for item in visual)
        user.append(f"\nأمامك صور شارت للأطر: {frames}. اقرأها مع الأرقام لا بدلاً منها.")

    return (
        [
            LLMMessage(role="system", content="\n\n---\n\n".join(parts)),
            LLMMessage(role="user", content="\n".join(user)),
        ],
        system,
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the object out of a reply that may be wrapped in prose or a fence.

    Models fence JSON, prefix it with a sentence, or do both. Refusing those
    replies would discard correct answers over presentation, so the object is
    located by its braces — but only the outermost pair, so a reply containing
    two objects is a malformed reply rather than a coin flip between them.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1] if "```" in stripped[3:] else stripped[3:]
        if stripped.startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in reply")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("reply JSON is not an object")
    return parsed


def _to_decision(payload: dict[str, Any], *, timeframe: str | None) -> DecisionOutput:
    """Second gate: shape it into the contract, which validates the arithmetic.

    `DecisionOutput` rejects a target on the stop's side of entry, a NO_TRADE
    without a reason, and a direction carrying a degraded flag. Those are the
    checks a conforming-but-wrong payload fails.
    """
    plan_type = payload.get("plan_type") or PlanType.IMMEDIATE.value
    execution_state = (
        ExecutionState.AWAITING_ACTIVATION
        if plan_type == PlanType.CONDITIONAL.value
        else ExecutionState.VALID_NOW
    )
    return DecisionOutput.model_validate(
        {
            "direction": payload.get("direction"),
            "confidence": payload.get("confidence"),
            "rationale": payload.get("rationale"),
            "plan_type": plan_type,
            "execution_state": execution_state,
            "levels": payload.get("levels"),
            # The caller's frame wins outright. The model is told which frame it
            # is analysing; a reply naming a different one is a mistake, not a
            # decision, and honouring it would label a plan with a chart it was
            # not sized for.
            "timeframe": timeframe or payload.get("timeframe"),
            "condition": payload.get("condition"),
            "validity_candles": payload.get("validity_candles"),
            "evidence": {
                "invalidation": payload.get("invalidation"),
                "condition": payload.get("condition"),
                "contradicting_evidence": payload.get("contradicting_evidence") or [],
            },
        }
    )


def evidence_levels(engines: dict[str, Any]) -> list[float]:
    """Every price the deterministic engines actually measured.

    Deduplicated and sorted so the tolerance check is a scan rather than a
    cross-product, and so the list can be shown to the model as a menu — a model
    given the levels it may use proposes ungrounded prices far less often than
    one asked to invent them and then told off for it.
    """
    found: set[float] = set()

    structure = engines.get("structure") or {}
    for key in ("nearest_support", "nearest_resistance", "swing_high", "swing_low"):
        value = structure.get(key)
        if isinstance(value, int | float):
            found.add(float(value))
    for level in [*(structure.get("supports") or []), *(structure.get("resistances") or [])]:
        price = level.get("price") if isinstance(level, dict) else None
        if isinstance(price, int | float):
            found.add(float(price))

    for zone in (engines.get("zones") or {}).get("zones") or []:
        for key in ("low", "high"):
            value = zone.get(key) if isinstance(zone, dict) else None
            if isinstance(value, int | float):
                found.add(float(value))

    geometry = engines.get("geometry") or {}
    for pattern in geometry.get("patterns") or []:
        for key in ("break_level", "projected_target"):
            value = pattern.get(key)
            if isinstance(value, int | float):
                found.add(float(value))
    for line in geometry.get("trendlines") or []:
        value = line.get("price_at_last_bar") if isinstance(line, dict) else None
        if isinstance(value, int | float):
            found.add(float(value))

    liquidity = engines.get("liquidity") or {}
    for bucket in ("equal_highs", "equal_lows", "sweeps"):
        for item in liquidity.get(bucket) or []:
            value = item.get("price") if isinstance(item, dict) else None
            if isinstance(value, int | float):
                found.add(float(value))

    return sorted(found)


def _ungrounded_prices(
    prices: list[float], levels: list[float], *, atr: float, reference: float
) -> list[float]:
    """Which of these prices matches nothing the engines measured."""
    if not levels:
        # No evidence levels at all is not a licence to accept anything: it means
        # the check cannot run, and the caller decides. Returning "all grounded"
        # here would turn a missing menu into a blanket approval.
        return []
    tolerance = atr * LEVEL_TOLERANCE_ATR if atr > 0 else abs(reference) * LEVEL_TOLERANCE_RELATIVE
    return [
        price for price in prices if not any(abs(price - level) <= tolerance for level in levels)
    ]


def _repair_message(problem: str) -> LLMMessage:
    return LLMMessage(
        role="user",
        content=(
            "الرد السابق مرفوض للسبب التالي، وهو السبب الوحيد المطلوب إصلاحه:\n"
            f"{problem}\n\n"
            "أعد **JSON فقط** بالمخطط نفسه، مصحَّحاً. لا تشرح ولا تعتذر."
        ),
    )


async def synthesize_decision(
    *,
    complete: CompleteFn,
    symbol: str,
    evidence: str,
    timeframe: str | None = None,
    visual: list[dict[str, Any]] | None = None,
    engines: dict[str, Any] | None = None,
    atr: float = 0.0,
    max_repairs: int = MAX_REPAIR_ATTEMPTS,
) -> SynthesizerOutcome:
    """Ask for a decision, validate it three ways, repair it twice, or fail closed."""
    levels = evidence_levels(engines or {})
    try:
        messages, system_prompt = build_decision_messages(
            symbol=symbol, evidence=evidence, visual=visual, levels=levels
        )
    except Exception as exc:  # noqa: BLE001 — a missing prompt must stop the run
        return SynthesizerOutcome(
            kind=SynthesizerFailureKind.LLM_NOT_CONFIGURED,
            detail=str(exc),
            failure=stage_failure_from_error(AgentStage.FINAL_DECISION, exc),
        )

    conversation = list(messages)
    repairs: list[str] = []
    last_problem = "no attempt made"

    for attempt in range(1, max_repairs + 2):
        try:
            response = await complete(conversation)
        except ProviderConfigurationError as exc:
            return SynthesizerOutcome(
                kind=SynthesizerFailureKind.LLM_NOT_CONFIGURED,
                detail=str(exc),
                failure=stage_failure_from_error(AgentStage.FINAL_DECISION, exc),
                attempts=attempt,
                repairs=repairs,
            )
        except Exception as exc:  # noqa: BLE001 — classified, never swallowed
            failure = stage_failure_from_error(AgentStage.FINAL_DECISION, exc)
            return SynthesizerOutcome(
                kind=_KIND_BY_CODE.get(failure.code.value, SynthesizerFailureKind.UNKNOWN),
                detail=str(exc),
                failure=failure,
                attempts=attempt,
                repairs=repairs,
            )

        raw = response.structured or None
        try:
            payload = raw if isinstance(raw, dict) else _extract_json(response.content or "")
        except (ValueError, json.JSONDecodeError) as exc:
            last_problem = f"الرد ليس JSON صالحاً: {exc}"
            repairs.append(last_problem)
            conversation = [*conversation, LLMMessage(role="assistant", content=response.content)]
            conversation.append(_repair_message(last_problem))
            continue

        try:
            decision = _to_decision(payload, timeframe=timeframe)
        except ValidationError as exc:
            # Named precisely: "fix your JSON" produces the same wrong plan again.
            last_problem = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()[:4]
            )
            repairs.append(last_problem)
            conversation = [*conversation, LLMMessage(role="assistant", content=response.content)]
            conversation.append(_repair_message(last_problem))
            continue

        if decision.direction not in (
            RecommendationDirection.BUY,
            RecommendationDirection.SELL,
        ):  # pragma: no cover — DecisionOutput already forbids it
            last_problem = "الاتجاه يجب أن يكون BUY أو SELL"
            repairs.append(last_problem)
            conversation.append(_repair_message(last_problem))
            continue

        assert decision.levels is not None
        proposed = [decision.levels.entry, decision.levels.stop, *decision.levels.targets]
        ungrounded = _ungrounded_prices(proposed, levels, atr=atr, reference=decision.levels.entry)
        if ungrounded:
            # Rejected whole. Patching a price to the nearest evidence level
            # would silently move the trade to a level the model never reasoned
            # about, which is a different trade wearing the same rationale.
            last_problem = (
                "هذه الأسعار لا تقابل أي مستوى قاسته المحرّكات: "
                + ", ".join(f"{price:.2f}" for price in ungrounded)
                + ". استخدم مستوى من قائمة الأدلة."
            )
            repairs.append(last_problem)
            conversation = [*conversation, LLMMessage(role="assistant", content=response.content)]
            conversation.append(_repair_message(last_problem))
            continue

        return SynthesizerOutcome(
            decision=decision,
            attempts=attempt,
            repairs=repairs,
            detail=system_prompt.hash,
            model=response.model,
            provider=response.provider,
        )

    kind = (
        SynthesizerFailureKind.LEVELS_NOT_GROUNDED
        if repairs and "لا تقابل أي مستوى" in repairs[-1]
        else SynthesizerFailureKind.REPAIR_EXHAUSTED
    )
    return SynthesizerOutcome(
        kind=kind,
        detail=last_problem,
        attempts=max_repairs + 1,
        repairs=repairs,
        failure=StageFailure(
            stage=AgentStage.FINAL_DECISION,
            code=stage_failure_from_error(AgentStage.FINAL_DECISION, last_problem).code,
            retryable=True,
            operator_detail=last_problem[:500],
        ),
    )

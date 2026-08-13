"""Gates a review found missing, pinned so they cannot come back.

Every case here was reachable in production and produced a confident wrong
answer or a 500. None of them failed a test before this file existed.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.agents.orchestrator import _DEGRADED_REASON_BY_KIND, run_analysis_orchestrator
from app.agents.synthesizer import SynthesizerFailureKind
from app.core.timeframes import DECISION_TIMEFRAMES
from app.models.enums import RecommendationDirection, Timeframe
from app.schemas.decision import DegradedReason
from app.tests.bars import swinging_bars

pytestmark = pytest.mark.no_db


def _candles(count: int = 140) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            open=Decimal(str(bar.open)),
            high=Decimal(str(bar.high)),
            low=Decimal(str(bar.low)),
            close=Decimal(str(bar.close)),
            ts=bar.ts,
            timeframe=Timeframe.M15,
        )
        for bar in swinging_bars(18, drift=3.0, swing=9.0, bars_per_leg=4)[:count]
    ]


@pytest.mark.asyncio
async def test_no_candles_fails_closed_instead_of_raising() -> None:
    """A provider that returned nothing used to become a 500 with no explanation.

    It is the same kind of missing input as every other, and gets the same kind
    of answer.
    """
    result = await run_analysis_orchestrator(symbol="XAUUSD", candles=[])
    assert result.decision["direction"] == RecommendationDirection.NO_TRADE.value
    assert result.decision["degraded_reason"] == "NO_CANDLES"
    assert result.decision["confidence"] is None


@pytest.mark.asyncio
async def test_the_model_cannot_rename_the_frame_the_selector_chose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D11 gives the choice to the agent's analysis, not to a returned string.

    Honouring the reply's own `timeframe` published a plan sized on one chart
    and labelled with another — verified reachable with a stub returning "H4".
    """
    import json

    from app.providers.llm.base import LLMResponse

    monkeypatch.setattr("app.agents.orchestrator.unavailable_engines", lambda _e: [])

    plan = {
        "direction": "BUY",
        "confidence": 0.6,
        "plan_type": "IMMEDIATE",
        # A frame the agent never selected, and not even a decision frame.
        "timeframe": "H4",
        "levels": {"entry": 2000.0, "stop": 1990.0, "targets": [2020.0]},
        "rationale": "x",
        "invalidation": "y",
    }

    class _Stub:
        async def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            return LLMResponse(
                content=json.dumps(plan), model="m", provider="p", usage={"total_tokens": 1}
            )

    result = await run_analysis_orchestrator(
        symbol="XAUUSD",
        candles=_candles(),
        llm=_Stub(),  # type: ignore[arg-type]
    )
    published = result.decision.get("timeframe")
    if not result.decision.get("degraded"):
        assert published != "H4"
        assert published in {tf.value for tf in DECISION_TIMEFRAMES}


def test_every_synthesizer_failure_maps_to_its_own_reason() -> None:
    """Collapsing them made an ungrounded plan indistinguishable from a missing
    API key in `agent_runs.error` — the one field an operator reads to tell a
    model problem from a deployment problem."""
    for kind in SynthesizerFailureKind:
        assert kind in _DEGRADED_REASON_BY_KIND, f"{kind} has no degraded reason"

    grounding = _DEGRADED_REASON_BY_KIND[SynthesizerFailureKind.LEVELS_NOT_GROUNDED]
    missing_key = _DEGRADED_REASON_BY_KIND[SynthesizerFailureKind.LLM_NOT_CONFIGURED]
    assert grounding != missing_key


def test_every_mapped_reason_exists_in_the_contract() -> None:
    known = {reason.value for reason in DegradedReason}
    assert set(_DEGRADED_REASON_BY_KIND.values()) <= known

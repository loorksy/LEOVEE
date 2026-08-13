from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.agents.orchestrator import run_analysis_orchestrator
from app.core.errors import ProviderConfigurationError
from app.models.enums import RecommendationDirection, Timeframe
from app.tests.bars import swinging_bars


def _candles(count: int = 140) -> list[SimpleNamespace]:
    """A realistic gold series: the analysis path now has real gates on it.

    A short, quiet, forex-priced series used to be enough here because every
    engine was a placeholder. It no longer is: the geometry engine wants sixty
    bars, and the agent's timeframe selection refuses a frame whose volatility
    cannot produce a first target clearing the round-trip cost. Both refusals
    fire before the narrative stage, so testing the LLM guarantee needs candles
    a real analysis would actually accept.
    """
    bars = swinging_bars(18, drift=3.0, swing=9.0, bars_per_leg=4)[:count]
    return [
        SimpleNamespace(
            open=Decimal(str(bar.open)),
            high=Decimal(str(bar.high)),
            low=Decimal(str(bar.low)),
            close=Decimal(str(bar.close)),
            ts=bar.ts,
            timeframe=Timeframe.M15,
        )
        for bar in bars
    ]


@pytest.mark.asyncio
async def test_orchestrator_fail_closed_when_llm_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LLM guarantee, tested with the engine layer pretending to be complete.

    The analytical engines are still placeholders and short-circuit the run
    before the narrative stage is reached (see app/engines/status.py), so the
    LLM branch is unreachable in production today. It is still the contract that
    matters most once M4 lands, so the engine gate is lifted here rather than
    letting this guarantee go untested until then.
    """
    monkeypatch.setattr("app.agents.orchestrator.unavailable_engines", lambda _engines: [])

    def boom() -> None:
        raise ProviderConfigurationError("No LLM provider API key configured")

    monkeypatch.setattr("app.agents.orchestrator.get_llm_provider", boom)

    result = await run_analysis_orchestrator(symbol="XAUUSD", candles=_candles())

    assert result.decision["direction"] == RecommendationDirection.NO_TRADE.value
    assert result.decision["confidence"] is None
    assert result.decision["degraded_reason"] == "LLM_UNAVAILABLE"
    assert "llm_unavailable" in result.narrative


@pytest.mark.asyncio
async def test_an_engine_that_cannot_answer_degrades_the_run() -> None:
    """A declining engine must stop the run, not be quietly analysed around.

    The engines are all implemented now, so this exercises the *live* refusal
    rather than a placeholder: a window too short for the geometry engine to
    confirm a pivot. Pricing risk and writing a narrative on top of evidence
    that is not there produces a confident, plausible, unfounded
    recommendation, which is exactly what the gate exists to prevent.
    """
    result = await run_analysis_orchestrator(symbol="XAUUSD", candles=_candles(count=30))

    assert result.decision["direction"] == RecommendationDirection.NO_TRADE.value
    assert result.decision["confidence"] is None
    assert result.decision["degraded_reason"] == "ENGINE_UNAVAILABLE"
    # The unmet dependencies are named, so the blocker has a cause rather than
    # just a request id.
    assert set(result.narrative["unavailable_engines"]) >= {"geometry", "structure"}
    assert result.decision["direction"] not in {
        RecommendationDirection.BUY.value,
        RecommendationDirection.SELL.value,
    }


@pytest.mark.asyncio
async def test_a_tape_no_scalping_frame_can_trade_fails_closed_with_its_own_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declining to trade is an answer, and a different one from a broken engine.

    Every scalping frame excluded — unreadable, too thin, or unable to clear its
    own costs — is more useful than a plan on a chart the agent has just
    established it cannot trade. It gets its own reason so the operator can tell
    a quiet market from a fault.
    """
    monkeypatch.setattr("app.agents.orchestrator.unavailable_engines", lambda _engines: [])
    quiet = [
        SimpleNamespace(
            open=Decimal(str(bar.open)),
            high=Decimal(str(bar.high)),
            low=Decimal(str(bar.low)),
            close=Decimal(str(bar.close)),
            ts=bar.ts,
            timeframe=Timeframe.M15,
        )
        for bar in swinging_bars(18, drift=0.02, swing=0.06, bars_per_leg=4)
    ]
    result = await run_analysis_orchestrator(symbol="XAUUSD", candles=quiet)

    assert result.decision["degraded_reason"] == "NO_VIABLE_TIMEFRAME"
    assert result.decision["confidence"] is None


@pytest.mark.asyncio
async def test_a_completed_run_reports_the_frame_the_agent_chose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frame is an output of the analysis, never an input from the user."""
    monkeypatch.setattr("app.agents.orchestrator.unavailable_engines", lambda _engines: [])

    def boom() -> None:
        raise ProviderConfigurationError("no key")

    monkeypatch.setattr("app.agents.orchestrator.get_llm_provider", boom)
    result = await run_analysis_orchestrator(symbol="XAUUSD", candles=_candles())

    selection = result.engines["timeframe_selection"]
    assert selection["timeframe"] == Timeframe.M15.value
    assert selection["candidates"]
    assert result.engines["plan_sanity"]["viable"] is True

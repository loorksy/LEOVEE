from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.agents.orchestrator import run_analysis_orchestrator
from app.core.datetime_utils import utc_now
from app.core.errors import ProviderConfigurationError
from app.models.enums import RecommendationDirection, Timeframe
from app.services.market.calendar import SessionStatus
from app.tests.bars import flat_bars, swinging_bars

_M15 = timedelta(minutes=15)


def _force_market_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the trading session open for the evidence gate.

    These tests verify what happens once a run reaches the LLM / decision stage
    — a missing provider fails closed, a completed run reports its frame. The
    evidence gate sits in front of that stage and, correctly, blocks a scalp on
    a closed gold market. Left to the wall clock the assertions would flip every
    weekend and every night, so the session is pinned here; the closed-market
    block itself is covered in ``test_evidence_gate.py``.
    """
    monkeypatch.setattr(
        "app.agents.orchestrator.get_session_status",
        lambda *_a, **_k: SessionStatus(is_open=True, reason="MARKET_OPEN"),
    )


def _candles(count: int = 140) -> list[SimpleNamespace]:
    """A realistic gold series: the analysis path now has real gates on it.

    A short, quiet, forex-priced series used to be enough here because every
    engine was a placeholder. It no longer is: the geometry engine wants sixty
    bars, and the agent's timeframe selection refuses a frame with no readable
    structure. Both refusals fire before the narrative stage, so testing the LLM
    guarantee needs candles a real analysis would actually accept.

    Timestamps end at *now*: the evidence gate refuses a scalp written on a stale
    price, so a live analysis reads fresh candles. A fixed historical fixture
    would (correctly) block on ``EVIDENCE_LIVE_PRICE`` before reaching the LLM.
    """
    bars = swinging_bars(18, drift=3.0, swing=9.0, bars_per_leg=4)[:count]
    base = utc_now()
    return [
        SimpleNamespace(
            open=Decimal(str(bar.open)),
            high=Decimal(str(bar.high)),
            low=Decimal(str(bar.low)),
            close=Decimal(str(bar.close)),
            ts=base - _M15 * (len(bars) - 1 - i),
            timeframe=Timeframe.M15,
        )
        for i, bar in enumerate(bars)
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
    _force_market_open(monkeypatch)

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

    Every scalping frame excluded — no readable shape, or too few bars — is more
    useful than a plan on a chart the agent has just established it cannot read.
    It gets its own reason so the operator can tell a dead tape from a fault.

    A dead tape, not a quiet one: a thin market used to land here too, excluded
    against a modelled cost floor. Now only the candles can exclude a frame, so
    the fixture is a chart with nothing on it rather than one that was merely
    cheap to disqualify.
    """
    monkeypatch.setattr("app.agents.orchestrator.unavailable_engines", lambda _engines: [])
    dead = [
        SimpleNamespace(
            open=Decimal(str(bar.open)),
            high=Decimal(str(bar.high)),
            low=Decimal(str(bar.low)),
            close=Decimal(str(bar.close)),
            ts=bar.ts,
            timeframe=Timeframe.M15,
        )
        for bar in flat_bars(120, price=2000.0, spread=0.001)
    ]
    result = await run_analysis_orchestrator(symbol="XAUUSD", candles=dead)

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

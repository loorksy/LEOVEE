from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.enums import RecommendationDirection, Timeframe
from app.models.market_artifacts import MarketEvent
from app.models.memory import AgentMemory
from app.models.recommendation import Thesis
from app.providers.market.base import NormalizedCandle
from app.services.analysis_service import run_analysis
from app.services.memory_service import retrieve_memories_for_symbol
from app.services.recommendation_service import get_recommendation
from app.tests.bars import swinging_bars
from app.tests.conftest import seed_user_org
from app.tests.doubles.llm import DecidingLLMProvider, FakeLLMProvider
from app.tests.doubles.market import FakeMarketDataProvider


def _gold_series(
    count: int = 200, *, timeframe: Timeframe = Timeframe.M15
) -> list[NormalizedCandle]:
    """A gold tape the engines can actually read.

    The fixture this replaces was 40 candles priced at 1.1000 and labelled
    XAUUSD — a currency pair wearing gold's name, from before ADR 0007, and
    twenty bars short of `MIN_CANDLES_FOR_ANALYSIS`. Every run on it failed
    closed on `ENGINE_UNAVAILABLE`, so the pipeline test could only ever cover
    the refusal path.

    A swinging series, not a ramp: a monotonic climb has no local extreme, so the
    swing detectors correctly find nothing and the structure engine reads
    `unknown` — which is the same dead end by a different route.
    """
    interval = timedelta(minutes=15 if timeframe is Timeframe.M15 else 60)
    sources = swinging_bars(24, start=2000.0, drift=3.0, swing=9.0, bars_per_leg=4)[:count]
    # End the tape at *now*: the evidence gate blocks a scalp written on a stale
    # price, so a completed directional plan needs a fresh series (a fixed
    # historical fixture would correctly fail closed on EVIDENCE_LIVE_PRICE).
    #
    # Emit newest-first. The provider double returns ``self._candles[:count]``
    # (the first 100 by default), so a chronological list would hand back its
    # oldest 100 bars and drop the freshly-stamped tail — the newest returned
    # candle would then be ~22h old and (correctly) fail the live-price check.
    # Newest-first keeps the fresh bars inside the fetch window; the store
    # re-orders by ts on read, so downstream sees a normal chronological tape.
    base = utc_now()
    candles = [
        NormalizedCandle(
            symbol="XAUUSD",
            timeframe=timeframe,
            ts=base - interval * (len(sources) - 1 - index),
            open=Decimal(str(round(source.open, 2))),
            high=Decimal(str(round(source.high, 2))),
            low=Decimal(str(round(source.low, 2))),
            close=Decimal(str(round(source.close, 2))),
            volume=Decimal("0"),
            complete=True,
            source="test_double",
        )
        for index, source in enumerate(sources)
    ]
    candles.reverse()
    return candles


@pytest.mark.asyncio
async def test_pipeline_market_to_thesis(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candles through to a stored recommendation, thesis and recallable memory.

    This covers the *wiring*, which holds regardless of what the analysis
    concludes. It deliberately does not assert an approved BUY/SELL: the
    analytical engines are placeholders until M4 (app/engines/status.py), so the
    run fails closed and the adversarial gate has nothing to approve. Forcing an
    approval here would mean stubbing the scenario engine as well, at which
    point the test would be checking its own stubs rather than the pipeline.

    What is asserted instead is the invariant that survives M4: the adversarial
    verdict and the decision agree with each other.
    """
    monkeypatch.setattr("app.agents.orchestrator.get_llm_provider", lambda: FakeLLMProvider())

    user, _org, _membership = await seed_user_org(db_session)
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)

    provider = FakeMarketDataProvider(_gold_series())
    result = await run_analysis(
        db_session,
        ctx,
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        market_provider=provider,
        complete_pipeline=True,
    )
    await db_session.commit()

    assert result["recommendation_id"]
    assert result["thesis_id"]
    assert result["memory_id"]

    # The adversarial gate must never approve a run that failed closed, and must
    # never withhold approval from one that succeeded without raising an issue.
    reasoning = result["reasoning"]
    adversarial = reasoning["adversarial"]
    decision_is_no_trade = result["decision"]["direction"] == RecommendationDirection.NO_TRADE.value
    assert adversarial["approved"] is not decision_is_no_trade, reasoning
    assert reasoning["approved"] == adversarial["approved"], reasoning
    if not adversarial["approved"]:
        assert adversarial["issues"], "a withheld approval must name its cause"

    rec = await get_recommendation(db_session, ctx, uuid.UUID(result["recommendation_id"]))
    await bind_workspace_rls(db_session, ctx)
    thesis = await db_session.scalar(
        select(Thesis).where(Thesis.id == uuid.UUID(result["thesis_id"]))
    )
    assert rec is not None
    assert thesis is not None
    assert thesis.recommendation_id == rec.id

    memory = await db_session.scalar(
        select(AgentMemory).where(AgentMemory.id == uuid.UUID(result["memory_id"]))
    )
    assert memory is not None
    assert memory.key.startswith("symbol:XAUUSD:analysis:")

    recalled = await retrieve_memories_for_symbol(
        db_session,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        symbol="XAUUSD",
    )
    assert any(item["id"] == result["memory_id"] for item in recalled)

    events = await db_session.execute(select(MarketEvent))
    assert len(events.scalars().all()) >= 1


@pytest.mark.asyncio
async def test_a_completed_analysis_publishes_a_directional_plan(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path a user actually gets, end to end, with nothing stubbed but the model.

    Every other pipeline test here exercises a refusal — no candles, no engine,
    no provider — which are the paths that must never publish. This is the one
    that must: real candles through real engines, a grounded plan back, and a
    stored recommendation carrying a direction (ADR 0002).

    The model double is not handed a plan. It reads the measured-level menu out
    of the prompt and builds one from those prices, so the grounding check is
    passed by construction rather than by the fixture agreeing with itself.
    """
    decider = DecidingLLMProvider(direction="BUY")
    monkeypatch.setattr("app.agents.orchestrator.get_llm_provider", lambda: decider)

    user, _org, _membership = await seed_user_org(db_session)
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)

    result = await run_analysis(
        db_session,
        ctx,
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        market_provider=FakeMarketDataProvider(_gold_series()),
        complete_pipeline=True,
    )
    await db_session.commit()

    decision = result["decision"]
    assert decision["direction"] == RecommendationDirection.BUY.value, decision
    assert decision.get("degraded") is not True, decision
    assert decision["confidence"] is not None
    # A completed analysis carries a full plan, not a direction on its own.
    assert decision["levels"]["entry"] and decision["levels"]["stop"]
    assert decision["levels"]["targets"]

    # D11: the frame is the agent's answer, and the payload reports *that* frame
    # rather than the series the caller happened to fetch.
    assert result["timeframe"] == result["engines"]["timeframe_selection"]["timeframe"]
    assert result["source_timeframe"] == Timeframe.M15.value

    # The plan went through the same tape check any plan would.
    assert result["engines"]["plan_sanity"]["viable"] is True

    rec = await get_recommendation(db_session, ctx, uuid.UUID(result["recommendation_id"]))
    assert rec is not None
    assert rec.direction is RecommendationDirection.BUY
    assert rec.entry is not None and rec.stop is not None
    assert rec.timeframe == decision["timeframe"]

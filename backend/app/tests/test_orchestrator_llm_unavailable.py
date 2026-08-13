from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.agents.orchestrator import run_analysis_orchestrator
from app.core.errors import ProviderConfigurationError
from app.models.enums import RecommendationDirection, Timeframe


def _candle(close: str = "1.1000") -> SimpleNamespace:
    price = Decimal(close)
    return SimpleNamespace(
        open=price,
        high=price + Decimal("0.001"),
        low=price - Decimal("0.001"),
        close=price,
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        timeframe=Timeframe.H1,
    )


def _candles(count: int = 30) -> list[SimpleNamespace]:
    return [_candle(str(Decimal("1.1000") + Decimal(i) * Decimal("0.0001"))) for i in range(count)]


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
async def test_orchestrator_fail_closed_while_engines_are_placeholders() -> None:
    """A placeholder engine must degrade the run, not be quietly analysed around."""
    result = await run_analysis_orchestrator(symbol="XAUUSD", candles=_candles())

    assert result.decision["direction"] == RecommendationDirection.NO_TRADE.value
    assert result.decision["confidence"] is None
    assert result.decision["degraded_reason"] == "ENGINE_UNAVAILABLE"
    # The unmet dependencies are named, so the blocker has a cause rather than
    # just a request id.
    assert set(result.narrative["unavailable_engines"]) >= {
        "liquidity",
        "scenarios",
        "structure",
        "zones",
    }
    assert result.decision["direction"] not in {
        RecommendationDirection.BUY.value,
        RecommendationDirection.SELL.value,
    }

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


@pytest.mark.asyncio
async def test_orchestrator_fail_closed_when_llm_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom() -> None:
        raise ProviderConfigurationError("No LLM provider API key configured")

    monkeypatch.setattr("app.agents.orchestrator.get_llm_provider", boom)

    candles = [_candle(str(Decimal("1.1000") + Decimal(i) * Decimal("0.0001"))) for i in range(30)]
    result = await run_analysis_orchestrator(symbol="EURUSD", candles=candles)

    assert result.decision["direction"] == RecommendationDirection.NO_TRADE.value
    assert result.decision["confidence"] is None
    assert result.decision["degraded_reason"] == "LLM_UNAVAILABLE"
    assert "llm_unavailable" in result.narrative

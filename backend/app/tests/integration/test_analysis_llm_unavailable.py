from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.core.tenant import resolve_tenant_context
from app.infrastructure.database import get_db_session
from app.main import app
from app.models.enums import RecommendationDirection, Timeframe
from app.models.symbol import Symbol
from app.providers.market.base import NormalizedCandle
from app.tests.conftest import seed_user_org


def _synthetic_h1_series(count: int = 40) -> list[NormalizedCandle]:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[NormalizedCandle] = []
    price = Decimal("1.1000")
    for i in range(count):
        ts = start + timedelta(hours=i)
        o = price + Decimal(i) * Decimal("0.0002")
        candles.append(
            NormalizedCandle(
                symbol="EURUSD",
                timeframe=Timeframe.H1,
                ts=ts,
                open=o,
                high=o + Decimal("0.0010"),
                low=o - Decimal("0.0008"),
                close=o + Decimal("0.0005"),
                volume=Decimal("0"),
                complete=True,
                source="test_double",
            )
        )
    return candles


@pytest.mark.asyncio
async def test_analysis_without_llm_returns_no_trade_never_directional(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §95: missing LLM must fail closed to NO_TRADE — never BUY/SELL with confidence."""
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()

    user, org, _ = await seed_user_org(
        db_session,
        email="analysis-no-llm@example.com",
        slug="analysis-no-llm",
    )
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None

    candles = _synthetic_h1_series()

    async def fake_fetch(
        session: AsyncSession,
        *,
        symbol_code: str,
        timeframe: Timeframe,
        provider: Any = None,
    ) -> tuple[Symbol, list[NormalizedCandle]]:
        row = Symbol(
            code=symbol_code,
            base_currency="EUR",
            quote_currency="USD",
            provider_mappings_json={},
        )
        session.add(row)
        await session.flush()
        return row, candles

    async def fake_mtf(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"mtf": {"trade_bias": "BULLISH"}, "intelligence_by_tf": {}}

    monkeypatch.setattr(
        "app.services.analysis_service.market_data.fetch_and_store_candles",
        fake_fetch,
    )
    monkeypatch.setattr("app.services.analysis_service.build_mtf_intelligence", fake_mtf)
    monkeypatch.setattr(
        "app.services.analysis_service.persist_engine_outputs",
        AsyncConst({}),
    )

    async def override_user() -> uuid.UUID:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analysis/run",
                json={"symbol": "EURUSD", "complete_pipeline": True},
                headers={
                    "X-Tenant-Id": str(org.id),
                    "X-Workspace-Id": str(ctx.workspace_id),
                },
            )
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200, response.text
    body = response.json()
    decision = body["decision"]
    assert decision["direction"] == RecommendationDirection.NO_TRADE.value
    assert decision.get("degraded_reason") == "LLM_UNAVAILABLE"
    assert decision.get("confidence") is None
    assert decision["direction"] not in {
        RecommendationDirection.BUY.value,
        RecommendationDirection.SELL.value,
    }
    assert "llm_unavailable" in (body.get("narrative") or {})


class AsyncConst:
    def __init__(self, value: Any) -> None:
        self._value = value

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._value

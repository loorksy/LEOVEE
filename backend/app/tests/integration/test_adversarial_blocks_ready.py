from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import OrchestratorResult
from app.api.deps import get_current_user_id
from app.core.tenant import resolve_tenant_context
from app.infrastructure.database import get_db_session
from app.main import app
from app.models.enums import RecommendationDirection, RecommendationStatus, Timeframe
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
async def test_adversarial_failure_blocks_ready_via_api(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, org, _ = await seed_user_org(
        db_session,
        email="adv-api@example.com",
        slug="adv-api",
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
        return {"mtf": {"trade_bias": "BEARISH"}, "intelligence_by_tf": {}}

    async def fake_orch(**_kwargs: Any) -> OrchestratorResult:
        return OrchestratorResult(
            agent_run_id=uuid.uuid4(),
            engines={"mtf": {"trade_bias": "BEARISH"}, "market_intelligence": {}},
            decision={
                "direction": RecommendationDirection.BUY.value,
                "confidence": 0.9,
            },
            narrative={},
        )

    monkeypatch.setattr(
        "app.services.analysis_service.market_data.fetch_and_store_candles",
        fake_fetch,
    )
    monkeypatch.setattr("app.services.analysis_service.build_mtf_intelligence", fake_mtf)
    monkeypatch.setattr("app.services.analysis_service.run_analysis_orchestrator", fake_orch)
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

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reasoning"]["approved"] is False
    assert body["reasoning"]["status"] == RecommendationStatus.FORMING.value
    assert body["reasoning"]["adversarial"]["issues"]


class AsyncConst:
    def __init__(self, value: Any) -> None:
        self._value = value

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._value

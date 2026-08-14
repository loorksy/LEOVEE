from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.tenant import resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.engines.chart_semantic import build_chart_semantic_model
from app.infrastructure.database import get_db_session
from app.main import app
from app.models.chart_annotation import ChartAnnotation
from app.services import chart_semantic_service
from app.tests.conftest import seed_user_org


@pytest.mark.asyncio
async def test_chart_semantic_persist_and_list(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session)
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    await bind_workspace_rls(db_session, ctx)

    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    engines = {
        "zones": {"zones": [{"type": "DEMAND", "low": 2000.0, "high": 2004.0}]},
        "liquidity": {"equal_highs": [{"price": 2030.0}]},
    }
    model = build_chart_semantic_model(
        symbol="XAUUSD",
        timeframe="M15",
        as_of=as_of,
        engines=engines,
        decision={
            "direction": "BUY",
            "levels": {"entry": 2005.0, "stop": 1998.0, "targets": [2018.0]},
        },
    )
    chart_semantic_service.validate_semantic_model(model.model_dump())
    rows = await chart_semantic_service.persist_semantic_model(db_session, ctx, model)
    await db_session.commit()
    assert len(rows) >= 2

    await bind_workspace_rls(db_session, ctx)
    listed = await chart_semantic_service.list_annotations(db_session, ctx)
    assert len(listed) >= len(rows)


@pytest.mark.asyncio
async def test_chart_api_create_annotation(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="chart-api@example.com", slug="chart-api")
    await db_session.commit()
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None

    async def override_user() -> object:
        return user.id

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_user
    app.dependency_overrides[get_db_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chart/annotations",
            json={
                "semantic_type": "price_line",
                "geometry_json": {
                    "anchors": [{"ts": "2024-01-01T00:00:00+00:00", "price": 1.2345}],
                },
                "style_json": {"label": "level"},
            },
            headers={
                "X-Tenant-Id": str(org.id),
                "X-Workspace-Id": str(ctx.workspace_id),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 201
    ann_id = response.json()["id"]

    await bind_workspace_rls(db_session, ctx)
    row = await db_session.scalar(
        select(ChartAnnotation).where(ChartAnnotation.id == uuid.UUID(ann_id))
    )
    assert row is not None
    assert row.semantic_type == "price_line"


@pytest.mark.asyncio
async def test_semantic_model_adapter_contract_shape() -> None:
    """§99: semantic operations must expose timestamp+price anchors for the chart adapter."""
    as_of = datetime(2024, 1, 1, tzinfo=UTC)
    model = build_chart_semantic_model(
        symbol="XAUUSD",
        timeframe="H1",
        as_of=as_of,
        engines={
            "zones": {"zones": [{"type": "DEMAND", "low": 2000.0, "high": 2004.0}]},
            "liquidity": {"equal_lows": [{"price": 1996.0}]},
        },
    )
    assert model.operations, "the contract is vacuous if nothing was produced"
    payload = model.model_dump()
    for op in payload["operations"]:
        for anchor in op["geometry"]["anchors"]:
            assert "ts" in anchor
            assert "price" in anchor
            assert "x" not in anchor and "y" not in anchor

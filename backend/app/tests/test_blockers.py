from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DataUnavailableError, ProviderConfigurationError
from app.core.startup import validate_production_startup
from app.core.tenant import resolve_tenant_context
from app.models.enums import Timeframe
from app.models.memory import MemoryType
from app.services import market_data
from app.services.learning.outcome_recorder import TerminalOutcome
from app.services.learning.pipeline import run_learning_pipeline
from app.services.memory_service import retrieve_memories_for_symbol, store_memory
from app.tests.conftest import seed_user_org
from app.tests.doubles.market import FakeMarketDataProvider


def test_production_startup_refuses_missing_credentials() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        SECRET_KEY="x" * 32,
        OANDA_API_TOKEN=None,
        OPENAI_API_KEY=None,
        ANTHROPIC_API_KEY=None,
    )
    with pytest.raises(ProviderConfigurationError):
        validate_production_startup(settings)


@pytest.mark.asyncio
async def test_market_provider_without_token_raises() -> None:
    from app.providers.market.oanda import OandaMarketDataProvider

    settings = Settings(OANDA_API_TOKEN=None)
    with pytest.raises(DataUnavailableError):
        OandaMarketDataProvider(settings)


@pytest.mark.asyncio
async def test_analysis_never_uses_synthetic_provider_candles(db_session: AsyncSession) -> None:
    await seed_user_org(db_session, email="nosynth@example.com", slug="nosynth")
    fake = FakeMarketDataProvider()
    with pytest.raises(DataUnavailableError):
        await market_data.fetch_and_store_candles(
            db_session,
            symbol_code="EURUSD",
            timeframe=Timeframe.H1,
            provider=fake,
        )


@pytest.mark.asyncio
async def test_learning_pipeline_updates_recall(db_session: AsyncSession) -> None:
    user, org, _ = await seed_user_org(db_session, email="learn@example.com", slug="learn")
    ctx = await resolve_tenant_context(db_session, user.id)
    assert ctx.workspace_id is not None
    symbol = await market_data.get_or_create_symbol(db_session, "EURUSD")

    await store_memory(
        db_session,
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        key="symbol:EURUSD",
        content={"confidence": 0.7, "sample_size": 5},
        memory_type=MemoryType.SEMANTIC,
    )

    terminal = TerminalOutcome(
        workspace_id=ctx.workspace_id,
        tenant_id=org.id,
        thesis_id=None,
        recommendation_id=uuid.uuid4(),
        trade_id=None,
        outcome="TARGET_REACHED",
        r_multiple=Decimal("1.5"),
        source="LIVE",
        facts={"strategy_code": "DEFAULT"},
        strategy_code="DEFAULT",
        setup_type="ANY",
        regime_bucket="TREND",
        session_bucket="LONDON",
        volatility_bucket="MID",
        symbol_id=symbol.id,
        confidence_stated=Decimal("0.7"),
        success=True,
    )
    await run_learning_pipeline(db_session, terminal)
    await db_session.flush()

    recalled = await retrieve_memories_for_symbol(
        db_session,
        tenant_id=org.id,
        workspace_id=ctx.workspace_id,
        symbol="EURUSD",
    )
    assert recalled
    profile_entry = recalled[0]
    assert profile_entry["key"] == "symbol:EURUSD"
    assert profile_entry["low_sample"] is True

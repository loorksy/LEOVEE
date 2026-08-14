"""The gold-only allowlist must gate the OUTBOUND call, not merely the result.

An earlier ordering fetched candles from the provider with the raw, unvalidated
symbol and only then ran the allowlist — so a rejected symbol still reached the
provider's URL with the platform's credentials. These tests pin that the
provider is never called for a symbol outside the allowlist.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.core.symbols import UnknownSymbolError
from app.models.enums import Timeframe
from app.providers.market.base import MarketDataProvider
from app.services import market_data

pytestmark = pytest.mark.no_db


class _RecordingProvider:
    """A provider double that records whether it was ever asked to fetch."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_candles(self, symbol: str, *, granularity: str, count: int) -> list[Any]:
        self.calls.append(symbol)
        return []

    async def fetch_candles_from(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise NotImplementedError


async def test_a_disallowed_symbol_never_reaches_the_provider() -> None:
    provider = _RecordingProvider()
    with pytest.raises(UnknownSymbolError):
        await market_data.fetch_and_store_candles(
            cast(Any, None),  # session is never touched — the gate raises first
            symbol_code="EURUSD",
            timeframe=Timeframe.M15,
            provider=cast(MarketDataProvider, provider),
        )
    assert provider.calls == []


async def test_a_path_traversal_symbol_never_reaches_the_provider() -> None:
    provider = _RecordingProvider()
    with pytest.raises(UnknownSymbolError):
        await market_data.fetch_and_store_candles(
            cast(Any, None),
            symbol_code="X_/../../v3",
            timeframe=Timeframe.M15,
            provider=cast(MarketDataProvider, provider),
        )
    assert provider.calls == []

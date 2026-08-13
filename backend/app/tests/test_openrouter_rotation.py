from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings, get_settings
from app.core.errors import ProviderConfigurationError
from app.providers.llm.base import LLMMessage
from app.providers.llm.common import normalize_provider_exception
from app.providers.llm.errors import LLMAuthError, LLMRateLimitError
from app.providers.llm.factory import get_llm_failover_chain, get_llm_provider
from app.providers.llm.openrouter import FreeModelRotatingProvider
from app.providers.llm.openrouter_catalog import (
    SEED_FREE_MODELS,
    advance_cursor,
    current_cursor,
    ordered_free_models,
    set_cached_free_models,
)


def _msgs() -> list[LLMMessage]:
    return [LLMMessage(role="user", content="hello")]


@pytest.fixture(autouse=True)
def _reset_catalog() -> Iterator[None]:
    set_cached_free_models(["model-a:free", "model-b:free", "model-c:free"])
    while current_cursor() != 0:
        advance_cursor()
    # Force cursor to 0
    from app.providers.llm import openrouter_catalog as cat

    cat._cursor = 0
    get_settings.cache_clear()
    yield
    set_cached_free_models(list(SEED_FREE_MODELS))
    cat._cursor = 0
    get_settings.cache_clear()


def test_quota_errors_are_retryable_for_rotation() -> None:
    err = normalize_provider_exception(Exception("402 Insufficient credits"))
    assert isinstance(err, LLMRateLimitError)
    assert err.retryable is True


def test_ordered_models_wrap_from_cursor() -> None:
    advance_cursor("model-a:free")
    assert ordered_free_models()[0] == "model-b:free"
    assert ordered_free_models()[-1] == "model-a:free"


@pytest.mark.asyncio
async def test_free_rotator_skips_exhausted_model() -> None:
    calls: list[str] = []

    class _FlakyChild:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, messages: list[LLMMessage], **kwargs: Any) -> Any:
            calls.append(self.model)
            if self.model == "model-a:free":
                raise LLMRateLimitError("rate limit on a")
            return MagicMock(
                content="ok",
                model=self.model,
                provider="openrouter",
                usage={"total_tokens": 1},
                structured=None,
                tool_calls=[],
            )

    rotator = FreeModelRotatingProvider("sk-or-test", models=["model-a:free", "model-b:free"])
    rotator._child = lambda model: _FlakyChild(model)  # type: ignore[method-assign,return-value,assignment]
    rotator.ensure_catalog = AsyncMock(return_value=["model-a:free", "model-b:free"])  # type: ignore[method-assign]

    out = await rotator.complete(_msgs())
    assert out.content == "ok"
    assert calls == ["model-a:free", "model-b:free"]
    # Cached catalog is [a,b,c]; success on b advances cursor to c (index 2).
    assert ordered_free_models()[0] == "model-c:free"


@pytest.mark.asyncio
async def test_free_rotator_raises_auth_without_rotating_all() -> None:
    class _AuthChild:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, messages: list[LLMMessage], **kwargs: Any) -> Any:
            raise LLMAuthError("bad key")

    rotator = FreeModelRotatingProvider("sk-or-test", models=["model-a:free", "model-b:free"])
    rotator._child = lambda model: _AuthChild(model)  # type: ignore[method-assign,return-value,assignment]
    rotator.ensure_catalog = AsyncMock(return_value=["model-a:free", "model-b:free"])  # type: ignore[method-assign]

    with pytest.raises(LLMAuthError):
        await rotator.complete(_msgs())


def test_factory_uses_openrouter_when_dedicated_keys_missing() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        OPENROUTER_API_KEY="sk-or-test",
        OPENAI_API_KEY="",
        ANTHROPIC_API_KEY="",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, FreeModelRotatingProvider)

    chain = get_llm_failover_chain(settings)
    assert len(chain) >= 2
    assert all(label.startswith("openrouter:") for label, _ in chain)


def test_factory_prefers_openai_then_openrouter_chain() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        OPENAI_API_KEY="sk-openai",
        OPENROUTER_API_KEY="sk-or-test",
        ANTHROPIC_API_KEY="",
    )
    chain = get_llm_failover_chain(settings)
    assert chain[0][0] == "openai"
    assert any(label.startswith("openrouter:") for label, _ in chain)


def test_factory_errors_without_any_llm_key() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        OPENAI_API_KEY="",
        ANTHROPIC_API_KEY="",
        OPENROUTER_API_KEY="",
    )
    with pytest.raises(ProviderConfigurationError):
        get_llm_provider(settings)

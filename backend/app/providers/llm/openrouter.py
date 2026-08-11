"""OpenRouter LLM provider with free-model rotation.

OpenRouter is OpenAI-compatible. Free models (``*:free`` / zero pricing) are
rotated round-robin: when a model hits rate/quota limits we advance to the next
and wrap the catalog — an ongoing loop across requests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.errors import ProviderConfigurationError
from app.providers.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMStreamChunk
from app.providers.llm.common import normalize_provider_exception
from app.providers.llm.errors import LLMError
from app.providers.llm.openai import OpenAIProvider
from app.providers.llm.openrouter_catalog import (
    advance_cursor,
    ordered_free_models,
    refresh_free_models_from_api,
)

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def openrouter_provider(
    api_key: str,
    *,
    model: str,
    client: Any | None = None,
    base_url: str = DEFAULT_OPENROUTER_BASE_URL,
    site_url: str = "https://leovee.lork.cloud",
    app_name: str = "Leovee",
) -> OpenAIProvider:
    if not api_key:
        raise ProviderConfigurationError("OpenRouter API key is not configured")
    return OpenAIProvider(
        api_key,
        model=model,
        client=client,
        base_url=base_url.rstrip("/"),
        default_headers={
            "HTTP-Referer": site_url,
            "X-Title": app_name,
        },
        provider_name="openrouter",
    )


def _is_rotatable_failure(exc: BaseException) -> bool:
    if isinstance(exc, LLMError):
        return bool(exc.retryable)
    normalized = normalize_provider_exception(exc)
    return bool(normalized.retryable)


class FreeModelRotatingProvider:
    """LLMProvider that walks the OpenRouter free catalog until one model succeeds."""

    def __init__(
        self,
        api_key: str,
        *,
        client: Any | None = None,
        base_url: str = DEFAULT_OPENROUTER_BASE_URL,
        models: list[str] | None = None,
        max_rounds: int = 1,
    ) -> None:
        if not api_key:
            raise ProviderConfigurationError("OpenRouter API key is not configured")
        self._api_key = api_key
        self._client = client
        self._base_url = base_url
        self._models_override = models
        self._max_rounds = max(1, max_rounds)

    def _models(self) -> list[str]:
        if self._models_override is not None:
            return list(self._models_override)
        return ordered_free_models()

    def _child(self, model: str) -> OpenAIProvider:
        return openrouter_provider(
            self._api_key,
            model=model,
            client=self._client,
            base_url=self._base_url,
        )

    async def ensure_catalog(self) -> list[str]:
        if self._models_override is not None:
            return list(self._models_override)
        return await refresh_free_models_from_api(api_key=self._api_key, base_url=self._base_url)

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> LLMResponse:
        await self.ensure_catalog()
        models = self._models()
        if not models:
            raise ProviderConfigurationError("No OpenRouter free models available")

        last_error: Exception | None = None
        # One full walk starting at the cursor; optional extra rounds for transient blips.
        attempts = models * self._max_rounds
        for model in attempts:
            child = self._child(model)
            try:
                # Avoid burning retries on a single exhausted free model — rotate instead.
                response = await child.complete(
                    messages,
                    response_format=response_format,
                    tools=tools,
                    timeout_seconds=timeout_seconds,
                    max_retries=0 if max_retries is None else max_retries,
                )
                advance_cursor(model)
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = normalize_provider_exception(exc)
                if not _is_rotatable_failure(last_error):
                    raise last_error from exc
                advance_cursor(model)
                continue
        assert last_error is not None
        raise last_error

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        await self.ensure_catalog()
        models = self._models()
        if not models:
            raise ProviderConfigurationError("No OpenRouter free models available")

        last_error: Exception | None = None
        for model in models * self._max_rounds:
            child = self._child(model)
            yielded_tokens = False
            try:
                async for chunk in child.stream(messages, timeout_seconds=timeout_seconds):
                    if chunk.text:
                        yielded_tokens = True
                    yield chunk
                    if chunk.done:
                        advance_cursor(model)
                        return
            except Exception as exc:  # noqa: BLE001
                last_error = normalize_provider_exception(exc)
                if yielded_tokens or not _is_rotatable_failure(last_error):
                    raise last_error from exc
                advance_cursor(model)
                continue
        assert last_error is not None
        raise last_error


def build_openrouter_free_chain(
    api_key: str,
    *,
    client: Any | None = None,
    base_url: str = DEFAULT_OPENROUTER_BASE_URL,
    models: list[str] | None = None,
) -> list[tuple[str, LLMProvider]]:
    """Expand free models into a labeled failover chain for SSE stream_reset."""
    catalog = models if models is not None else ordered_free_models()
    chain: list[tuple[str, LLMProvider]] = []
    for model in catalog:
        chain.append(
            (
                f"openrouter:{model}",
                openrouter_provider(api_key, model=model, client=client, base_url=base_url),
            )
        )
    return chain

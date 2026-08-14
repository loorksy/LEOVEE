from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ProviderConfigurationError
from app.models.model_config import ModelConfig
from app.observability.prometheus import llm_tokens_total
from app.providers.llm.anthropic import AnthropicProvider
from app.providers.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.providers.llm.errors import LLMError, LLMRateLimitError
from app.providers.llm.factory import get_llm_provider
from app.providers.llm.openai import OpenAIProvider
from app.providers.llm.openrouter import FreeModelRotatingProvider, openrouter_provider


@dataclass
class RouterFailure:
    task: str
    provider: str
    error_code: str
    message: str
    at: float = field(default_factory=time.time)


@dataclass
class _RateBucket:
    window_start: float
    count: int = 0


class ModelRouter:
    """Task-based LLM routing with fallback, cost caps, and rate limits (Phase 17)."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        max_requests_per_minute: int = 60,
        max_tokens_per_task: int = 50_000,
    ) -> None:
        self._settings = settings or get_settings()
        self._max_rpm = max_requests_per_minute
        self._max_tokens_per_task = max_tokens_per_task
        self._failures: list[RouterFailure] = []
        self._rate_buckets: dict[str, _RateBucket] = {}
        self._token_usage: dict[str, int] = defaultdict(int)

    @property
    def failures(self) -> list[RouterFailure]:
        return list(self._failures)

    def _provider_for(self, name: str, model: str | None = None) -> LLMProvider:
        if name == "openai":
            if not self._settings.openai_api_key:
                raise ProviderConfigurationError("OpenAI API key not configured")
            return OpenAIProvider(
                self._settings.openai_api_key,
                model=model or "gpt-4o-mini",
            )
        if name == "anthropic":
            if not self._settings.anthropic_api_key:
                raise ProviderConfigurationError("Anthropic API key not configured")
            return AnthropicProvider(
                self._settings.anthropic_api_key,
                model=model or "claude-3-5-haiku-latest",
            )
        if name == "openrouter":
            if not self._settings.openrouter_api_key:
                raise ProviderConfigurationError("OpenRouter API key not configured")
            if model:
                return openrouter_provider(
                    self._settings.openrouter_api_key,
                    model=model,
                    base_url=self._settings.openrouter_base_url,
                )
            return FreeModelRotatingProvider(
                self._settings.openrouter_api_key,
                base_url=self._settings.openrouter_base_url,
            )
        raise ProviderConfigurationError(f"Unknown provider: {name}")

    def _check_rate_limit(self, task: str) -> None:
        now = time.time()
        bucket = self._rate_buckets.get(task)
        if bucket is None or now - bucket.window_start >= 60:
            self._rate_buckets[task] = _RateBucket(window_start=now, count=1)
            return
        if bucket.count >= self._max_rpm:
            raise LLMRateLimitError(f"ModelRouter rate limit exceeded for task={task}")
        bucket.count += 1

    def _check_cost_control(self, task: str) -> None:
        if self._token_usage[task] >= self._max_tokens_per_task:
            raise LLMError(
                f"ModelRouter cost control: token budget exhausted for task={task}",
                code="llm_cost_limit",
                retryable=False,
            )

    def record_usage(
        self, task: str, usage: dict[str, int], *, provider: str = "", model: str = ""
    ) -> None:
        # Prometheus alongside the budget ledger: the ledger answers "may this
        # task spend more", the counter answers "what did this deploy spend" —
        # different questions, and the second used to vanish on every restart.
        if provider or model:
            llm_tokens_total.labels(provider or "unknown", model or "unknown", "prompt").inc(
                int(usage.get("prompt_tokens") or 0)
            )
            llm_tokens_total.labels(provider or "unknown", model or "unknown", "completion").inc(
                int(usage.get("completion_tokens") or 0)
            )
        total = int(usage.get("total_tokens") or 0)
        if total <= 0:
            total = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
        self._token_usage[task] += total

    async def resolve(self, session: AsyncSession, task: str) -> LLMProvider:
        row = await session.scalar(
            select(ModelConfig).where(ModelConfig.task == task, ModelConfig.enabled)
        )
        if row is None:
            return get_llm_provider(self._settings)
        try:
            return self._provider_for(row.primary_provider, row.primary_model)
        except ProviderConfigurationError:
            if row.fallback_provider:
                return self._provider_for(row.fallback_provider, row.fallback_model)
            raise

    async def complete(
        self,
        session: AsyncSession,
        task: str,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        provider_override: LLMProvider | None = None,
        fallback_override: LLMProvider | None = None,
    ) -> LLMResponse:
        """Resolve provider by task and execute with runtime fallback.

        If the primary provider fails at call time, the fallback provider is used
        and the primary failure is recorded on ``self.failures``.
        """
        self._check_rate_limit(task)
        self._check_cost_control(task)

        row = await session.scalar(
            select(ModelConfig).where(ModelConfig.task == task, ModelConfig.enabled)
        )
        primary_name = row.primary_provider if row else "default"
        fallback_name = row.fallback_provider if row else None

        primary = provider_override
        if primary is None:
            if row is None:
                primary = get_llm_provider(self._settings)
            else:
                primary = self._provider_for(row.primary_provider, row.primary_model)

        try:
            response = await primary.complete(
                messages,
                response_format=response_format,
                tools=tools,
            )
            self.record_usage(
                task, response.usage, provider=response.provider, model=response.model
            )
            return response
        except Exception as primary_exc:  # noqa: BLE001
            code = getattr(primary_exc, "code", type(primary_exc).__name__)
            self._failures.append(
                RouterFailure(
                    task=task,
                    provider=str(primary_name),
                    error_code=str(code),
                    message=str(primary_exc),
                )
            )
            fallback = fallback_override
            if fallback is None:
                if row is None or not fallback_name:
                    raise
                fallback = self._provider_for(fallback_name, row.fallback_model)
            response = await fallback.complete(
                messages,
                response_format=response_format,
                tools=tools,
            )
            self.record_usage(
                task, response.usage, provider=response.provider, model=response.model
            )
            return response

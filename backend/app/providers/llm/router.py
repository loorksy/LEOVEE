from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ProviderConfigurationError
from app.models.model_config import ModelConfig
from app.providers.llm.anthropic import AnthropicProvider
from app.providers.llm.base import LLMProvider
from app.providers.llm.factory import get_llm_provider
from app.providers.llm.openai import OpenAIProvider


class ModelRouter:
    """Task-based LLM routing with optional fallback (Phase 17)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _provider_for(self, name: str) -> LLMProvider:
        if name == "openai":
            if not self._settings.openai_api_key:
                raise ProviderConfigurationError("OpenAI API key not configured")
            return OpenAIProvider(self._settings.openai_api_key)
        if name == "anthropic":
            if not self._settings.anthropic_api_key:
                raise ProviderConfigurationError("Anthropic API key not configured")
            return AnthropicProvider(self._settings.anthropic_api_key)
        raise ProviderConfigurationError(f"Unknown provider: {name}")

    async def resolve(self, session: AsyncSession, task: str) -> LLMProvider:
        row = await session.scalar(
            select(ModelConfig).where(ModelConfig.task == task, ModelConfig.enabled)
        )
        if row is None:
            return get_llm_provider(self._settings)
        try:
            return self._provider_for(row.primary_provider)
        except ProviderConfigurationError:
            if row.fallback_provider:
                return self._provider_for(row.fallback_provider)
            raise

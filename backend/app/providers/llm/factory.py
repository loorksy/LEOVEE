from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ProviderConfigurationError
from app.providers.llm.anthropic import AnthropicProvider
from app.providers.llm.base import LLMProvider
from app.providers.llm.openai import OpenAIProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    from app.core.config import get_settings

    resolved = settings or get_settings()
    if resolved.openai_api_key:
        return OpenAIProvider(resolved.openai_api_key)
    if resolved.anthropic_api_key:
        return AnthropicProvider(resolved.anthropic_api_key)
    raise ProviderConfigurationError("No LLM provider API key configured")

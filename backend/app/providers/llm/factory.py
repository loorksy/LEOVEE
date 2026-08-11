from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ProviderConfigurationError
from app.providers.llm.anthropic import AnthropicProvider
from app.providers.llm.base import LLMProvider
from app.providers.llm.openai import OpenAIProvider
from app.providers.llm.openrouter import FreeModelRotatingProvider, build_openrouter_free_chain


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the preferred single provider (dedicated keys first, else OpenRouter free loop)."""
    from app.core.config import get_settings

    resolved = settings or get_settings()
    if resolved.openai_api_key:
        return OpenAIProvider(resolved.openai_api_key)
    if resolved.anthropic_api_key:
        return AnthropicProvider(resolved.anthropic_api_key)
    if resolved.openrouter_api_key:
        return FreeModelRotatingProvider(
            resolved.openrouter_api_key,
            base_url=resolved.openrouter_base_url,
        )
    raise ProviderConfigurationError(
        "No LLM provider API key configured "
        "(OPENAI_API_KEY, ANTHROPIC_API_KEY, or OPENROUTER_API_KEY)"
    )


def get_llm_failover_chain(settings: Settings | None = None) -> list[tuple[str, LLMProvider]]:
    """Ordered provider chain for chat streaming / complete failover.

    Dedicated OpenAI/Anthropic come first when configured. OpenRouter free models
    follow as an infinite round-robin catalog (cursor advances on rate/quota).
    """
    from app.core.config import get_settings

    resolved = settings or get_settings()
    chain: list[tuple[str, LLMProvider]] = []
    if resolved.openai_api_key:
        chain.append(("openai", OpenAIProvider(resolved.openai_api_key)))
    if resolved.anthropic_api_key:
        chain.append(("anthropic", AnthropicProvider(resolved.anthropic_api_key)))
    if resolved.openrouter_api_key:
        chain.extend(
            build_openrouter_free_chain(
                resolved.openrouter_api_key,
                base_url=resolved.openrouter_base_url,
            )
        )
    if not chain:
        raise ProviderConfigurationError(
            "No LLM provider API key configured "
            "(OPENAI_API_KEY, ANTHROPIC_API_KEY, or OPENROUTER_API_KEY)"
        )
    return chain

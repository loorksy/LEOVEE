from __future__ import annotations

from typing import Any

from app.core.errors import ProviderConfigurationError
from app.providers.llm.base import LLMMessage, LLMResponse


class AnthropicProvider:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ProviderConfigurationError("Anthropic API key is not configured")
        self._api_key = api_key

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self._api_key)
        system_msg = next((m.content for m in messages if m.role == "system"), "")
        user_msgs = [m for m in messages if m.role != "system"]
        kwargs: dict[str, object] = {
            "model": "claude-3-5-haiku-latest",
            "max_tokens": 1024,
            "messages": [{"role": m.role, "content": m.content} for m in user_msgs],
        }
        if system_msg:
            kwargs["system"] = system_msg
        response = await client.messages.create(**kwargs)  # type: ignore[call-overload]
        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        return LLMResponse(
            content=text,
            model=response.model,
            provider="anthropic",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

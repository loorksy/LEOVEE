from __future__ import annotations

from typing import Any

from app.providers.llm.base import LLMMessage, LLMProvider, LLMResponse, mock_structured_response


class AnthropicProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        if not self._api_key:
            structured = mock_structured_response(messages)
            return LLMResponse(
                content=structured["summary"],
                model="claude-3-5-haiku-mock",
                provider="anthropic",
                usage={"input_tokens": 10, "output_tokens": 20},
                structured=structured,
            )
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


def get_anthropic_provider(api_key: str | None = None) -> LLMProvider:
    return AnthropicProvider(api_key)

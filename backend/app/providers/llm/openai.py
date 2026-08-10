from __future__ import annotations

from typing import Any

from app.providers.llm.base import LLMMessage, LLMProvider, LLMResponse, mock_structured_response


class OpenAIProvider:
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
                model="gpt-4o-mini-mock",
                provider="openai",
                usage={"prompt_tokens": 10, "completion_tokens": 20},
                structured=structured,
            )
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        payload: list[dict[str, str]] = [{"role": m.role, "content": m.content} for m in messages]
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=payload,  # type: ignore[arg-type]
        )
        text = response.choices[0].message.content or ""
        return LLMResponse(
            content=text,
            model=response.model,
            provider="openai",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )


def get_openai_provider(api_key: str | None = None) -> LLMProvider:
    return OpenAIProvider(api_key)

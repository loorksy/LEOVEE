from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.core.errors import ProviderConfigurationError
from app.providers.llm.base import LLMMessage, LLMResponse, LLMStreamChunk, LLMToolCall
from app.providers.llm.common import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    parse_structured_content,
    to_openai_messages,
    to_openai_tools,
    usage_from_openai,
    with_timeout_retry,
)


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        client: Any | None = None,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
        provider_name: str = "openai",
    ) -> None:
        if not api_key:
            raise ProviderConfigurationError("OpenAI API key is not configured")
        self._api_key = api_key
        self._model = model
        self._client = client
        self._base_url = base_url
        self._default_headers = default_headers
        self._provider_name = provider_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._default_headers:
            kwargs["default_headers"] = self._default_headers
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        payload = to_openai_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": payload,
        }
        if response_format is not None:
            # Prefer native JSON mode when requesting structured output.
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        async def _call() -> Any:
            return await client.chat.completions.create(**kwargs)

        response = await with_timeout_retry(
            _call,
            timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            max_retries=max_retries if max_retries is not None else DEFAULT_MAX_RETRIES,
        )
        choice = response.choices[0].message
        text = choice.content or ""
        tool_calls: list[LLMToolCall] = []
        for tc in getattr(choice, "tool_calls", None) or []:
            raw_args = tc.function.arguments if tc.function else "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {"raw": raw_args}
            tool_calls.append(
                LLMToolCall(
                    id=str(tc.id),
                    name=str(tc.function.name),
                    arguments=args if isinstance(args, dict) else {"value": args},
                )
            )
        structured = parse_structured_content(text, response_format)
        return LLMResponse(
            content=text,
            model=response.model,
            provider=self._provider_name,
            usage=usage_from_openai(response.usage),
            structured=structured,
            tool_calls=tool_calls,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        client = self._get_client()
        payload = to_openai_messages(messages)

        async def _open() -> Any:
            return await client.chat.completions.create(
                model=self._model,
                messages=payload,
                stream=True,
                stream_options={"include_usage": True},
            )

        stream = await with_timeout_retry(
            _open,
            timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            max_retries=0,
        )
        usage: dict[str, int] = {}
        model = self._model
        async for event in stream:
            model = getattr(event, "model", None) or model
            if getattr(event, "usage", None) is not None:
                usage = usage_from_openai(event.usage)
            choices = getattr(event, "choices", None) or []
            if not choices:
                continue
            delta = choices[0].delta
            text = getattr(delta, "content", None) or ""
            if text:
                yield LLMStreamChunk(text=text, model=model, provider=self._provider_name)
        yield LLMStreamChunk(
            text="",
            model=model,
            provider=self._provider_name,
            done=True,
            usage=usage,
        )

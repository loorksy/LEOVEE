from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.errors import ProviderConfigurationError
from app.providers.llm.base import LLMMessage, LLMResponse, LLMStreamChunk, LLMToolCall
from app.providers.llm.common import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    parse_structured_content,
    usage_from_anthropic,
    with_timeout_retry,
)


class AnthropicProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-3-5-haiku-latest",
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ProviderConfigurationError("Anthropic API key is not configured")
        self._api_key = api_key
        self._model = model
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    def _split_messages(self, messages: list[LLMMessage]) -> tuple[str, list[dict[str, Any]]]:
        system_msg = next((m.content for m in messages if m.role == "system"), "")
        user_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        return system_msg, user_msgs

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
        system_msg, user_msgs = self._split_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": user_msgs,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if response_format is not None and system_msg == "":
            kwargs["system"] = "Respond with a single JSON object only."
        elif response_format is not None:
            kwargs["system"] = f"{system_msg}\nRespond with a single JSON object only."
        if tools:
            # Anthropic tool schema uses name/description/input_schema.
            kwargs["tools"] = tools

        async def _call() -> Any:
            return await client.messages.create(**kwargs)

        response = await with_timeout_retry(
            _call,
            timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            max_retries=max_retries if max_retries is not None else DEFAULT_MAX_RETRIES,
        )
        text_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            text_value = getattr(block, "text", None)
            if isinstance(text_value, str) and text_value:
                text_parts.append(text_value)
            if block_type == "tool_use":
                raw_input = getattr(block, "input", {}) or {}
                args = raw_input if isinstance(raw_input, dict) else {"raw": raw_input}
                tool_calls.append(
                    LLMToolCall(
                        id=str(getattr(block, "id", "")),
                        name=str(getattr(block, "name", "")),
                        arguments=args,
                    )
                )
        text = "".join(text_parts)
        structured = parse_structured_content(text, response_format)
        return LLMResponse(
            content=text,
            model=response.model,
            provider="anthropic",
            usage=usage_from_anthropic(response.usage),
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
        system_msg, user_msgs = self._split_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": user_msgs,
            "stream": True,
        }
        if system_msg:
            kwargs["system"] = system_msg

        async def _open() -> Any:
            return await client.messages.create(**kwargs)

        stream = await with_timeout_retry(
            _open,
            timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            max_retries=0,
        )
        usage: dict[str, int] = {}
        model = self._model
        async for event in stream:
            event_type = getattr(event, "type", None)
            if event_type == "content_block_delta":
                delta = getattr(event, "delta", None)
                text = getattr(delta, "text", None) or ""
                if text:
                    yield LLMStreamChunk(text=text, model=model, provider="anthropic")
            elif event_type == "message_start":
                message = getattr(event, "message", None)
                model = getattr(message, "model", None) or model
            elif event_type == "message_delta":
                u = getattr(event, "usage", None)
                if u is not None:
                    usage = usage_from_anthropic(u)
            # Some SDKs expose final usage outside message_delta.
            has_usage = hasattr(event, "usage") and event.usage is not None
            if has_usage and event_type != "message_delta":
                usage = usage_from_anthropic(event.usage)
        yield LLMStreamChunk(text="", model=model, provider="anthropic", done=True, usage=usage)

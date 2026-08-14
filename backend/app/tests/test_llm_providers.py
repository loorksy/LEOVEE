from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.providers.llm.anthropic import AnthropicProvider
from app.providers.llm.base import LLMMessage
from app.providers.llm.common import normalize_provider_exception, with_timeout_retry
from app.providers.llm.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMTimeoutError
from app.providers.llm.openai import OpenAIProvider
from app.providers.llm.router import ModelRouter
from app.tests.doubles.llm import FakeLLMProvider


def _msgs() -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content="sys"),
        LLMMessage(role="user", content="hello"),
    ]


class _AsyncIter:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def __aiter__(self) -> _AsyncIter:
        self._iter = iter(self._items)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_openai_generate_usage_structured_and_tools() -> None:
    tool = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="lookup", arguments='{"symbol":"XAUUSD"}'),
    )
    message = SimpleNamespace(content='{"ok":true}', tool_calls=[tool])
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        model="gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    provider = OpenAIProvider("test-key", client=client)

    out = await provider.complete(
        _msgs(),
        response_format={"type": "json_object"},
        tools=[{"type": "function", "function": {"name": "lookup"}}],
    )
    assert out.provider == "openai"
    assert out.usage["total_tokens"] == 18
    assert out.structured == {"ok": True}
    assert out.tool_calls[0].name == "lookup"
    assert out.tool_calls[0].arguments["symbol"] == "XAUUSD"
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["response_format"]["type"] == "json_object"
    assert kwargs["tools"]


@pytest.mark.asyncio
async def test_openai_stream_and_timeout_retry() -> None:
    events = [
        SimpleNamespace(
            model="gpt-4o-mini",
            usage=None,
            choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi"))],
        ),
        SimpleNamespace(
            model="gpt-4o-mini",
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            choices=[SimpleNamespace(delta=SimpleNamespace(content="!"))],
        ),
    ]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_AsyncIter(events))
    provider = OpenAIProvider("test-key", client=client)
    chunks = [c async for c in provider.stream(_msgs())]
    text = "".join(c.text for c in chunks if not c.done)
    assert text == "Hi!"
    assert chunks[-1].done is True
    assert chunks[-1].usage["total_tokens"] == 2

    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow")
        return "ok"

    result = await with_timeout_retry(flaky, timeout_seconds=1, max_retries=2, backoff_seconds=0)
    assert result == "ok"


@pytest.mark.asyncio
async def test_anthropic_generate_stream_tools_structured() -> None:
    tool_block = SimpleNamespace(
        type="tool_use",
        id="tu1",
        name="lookup",
        input={"symbol": "GBPUSD"},
        text=None,
    )
    text_block = SimpleNamespace(type="text", text='{"ok":true}')
    response = SimpleNamespace(
        content=[text_block, tool_block],
        model="claude-3-5-haiku-latest",
        usage=SimpleNamespace(input_tokens=9, output_tokens=4),
    )
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    provider = AnthropicProvider("test-key", client=client)
    out = await provider.complete(
        _msgs(),
        response_format={"type": "json_object"},
        tools=[{"name": "lookup", "input_schema": {"type": "object"}}],
    )
    assert out.provider == "anthropic"
    assert out.usage["input_tokens"] == 9
    assert out.structured == {"ok": True}
    assert out.tool_calls[0].arguments["symbol"] == "GBPUSD"

    stream_events = [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(model="claude-3-5-haiku-latest"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(text="A"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(text="B"),
        ),
        SimpleNamespace(
            type="message_delta",
            usage=SimpleNamespace(input_tokens=2, output_tokens=2),
        ),
    ]
    client.messages.create = AsyncMock(return_value=_AsyncIter(stream_events))
    chunks = [c async for c in provider.stream(_msgs())]
    assert "".join(c.text for c in chunks if not c.done) == "AB"
    assert chunks[-1].done is True


@pytest.mark.asyncio
async def test_streaming_parity_between_providers() -> None:
    oai_client = MagicMock()
    oai_client.chat.completions.create = AsyncMock(
        return_value=_AsyncIter(
            [
                SimpleNamespace(
                    model="gpt",
                    usage=None,
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="same"))],
                )
            ]
        )
    )
    ant_client = MagicMock()
    ant_client.messages.create = AsyncMock(
        return_value=_AsyncIter(
            [
                SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text="same")),
            ]
        )
    )
    oai_text = "".join(
        [c.text async for c in OpenAIProvider("k", client=oai_client).stream(_msgs()) if not c.done]
    )
    ant_text = "".join(
        [
            c.text
            async for c in AnthropicProvider("k", client=ant_client).stream(_msgs())
            if not c.done
        ]
    )
    assert oai_text == ant_text == "same"


def test_error_normalization() -> None:
    class AuthExc(Exception):
        status_code = 401

    class RateExc(Exception):
        status_code = 429

    assert isinstance(normalize_provider_exception(AuthExc("nope")), LLMAuthError)
    assert isinstance(normalize_provider_exception(RateExc("slow")), LLMRateLimitError)
    assert isinstance(normalize_provider_exception(TimeoutError("t")), LLMTimeoutError)


@pytest.mark.asyncio
async def test_model_router_task_selection_fallback_cost_and_rate(
    db_session: Any,
) -> None:
    from app.models.model_config import ModelConfig

    db_session.add(
        ModelConfig(
            task="narrative_test",
            primary_provider="openai",
            primary_model="gpt-4o-mini",
            fallback_provider="anthropic",
            fallback_model="claude-3-5-haiku-latest",
            enabled=True,
        )
    )
    await db_session.flush()

    settings = Settings(OPENAI_API_KEY="oai", ANTHROPIC_API_KEY="ant")
    router = ModelRouter(settings, max_requests_per_minute=2, max_tokens_per_task=10)
    primary = FakeLLMProvider(fail_times=1)
    fallback = FakeLLMProvider(content="fallback-ok")

    out = await router.complete(
        db_session,
        "narrative_test",
        _msgs(),
        provider_override=primary,
        fallback_override=fallback,
    )
    assert out.content == "fallback-ok"
    assert len(router.failures) == 1
    assert router.failures[0].provider == "openai"
    assert router.failures[0].task == "narrative_test"

    await router.complete(
        db_session,
        "narrative_test",
        _msgs(),
        provider_override=FakeLLMProvider(),
    )
    with pytest.raises(LLMRateLimitError):
        await router.complete(
            db_session,
            "narrative_test",
            _msgs(),
            provider_override=FakeLLMProvider(),
        )

    # Cost control: inflate usage then reject.
    router2 = ModelRouter(settings, max_requests_per_minute=100, max_tokens_per_task=1)
    router2.record_usage("narrative_test", {"total_tokens": 5})
    with pytest.raises(LLMError, match="cost control"):
        await router2.complete(
            db_session,
            "narrative_test",
            _msgs(),
            provider_override=FakeLLMProvider(),
        )


@pytest.mark.asyncio
async def test_openai_retries_then_normalizes_non_retryable() -> None:
    client = MagicMock()

    class Fatal(Exception):
        status_code = 400

    client.chat.completions.create = AsyncMock(side_effect=Fatal("bad request"))
    provider = OpenAIProvider("k", client=client)
    with pytest.raises(LLMError) as exc:
        await provider.complete(_msgs(), max_retries=1)
    assert exc.value.retryable is False

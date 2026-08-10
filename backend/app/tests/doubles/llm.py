from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.providers.llm.base import LLMMessage, LLMResponse, LLMStreamChunk


class FakeLLMProvider:
    """Test double only — inject via dependency overrides in tests."""

    def __init__(self, *, fail_times: int = 0, content: str | None = None) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self._content = content

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> LLMResponse:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("fake_primary_failure")
        last = messages[-1].content if messages else ""
        text = self._content if self._content is not None else f"Test narrative: {last[:80]}"
        structured = None
        if response_format is not None:
            structured = {
                "summary": f"Test analysis for: {last[:120]}",
                "confidence": 0.62,
                "bullets": ["test"],
            }
            text = (
                '{"summary":"Test analysis","confidence":0.62,"bullets":["test"]}'
                if self._content is None
                else self._content
            )
        return LLMResponse(
            content=text,
            model="test-model",
            provider="test",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            structured=structured
            or {
                "summary": f"Test analysis for: {last[:120]}",
                "confidence": 0.62,
                "bullets": ["test"],
            },
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        result = await self.complete(messages)
        for word in result.content.split():
            yield LLMStreamChunk(text=word + " ", model=result.model, provider=result.provider)
        yield LLMStreamChunk(
            text="",
            model=result.model,
            provider=result.provider,
            done=True,
            usage=result.usage,
        )

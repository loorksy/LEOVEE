from __future__ import annotations

from typing import Any

from app.providers.llm.base import LLMMessage, LLMResponse


class FakeLLMProvider:
    """Test double only — inject via dependency overrides in tests."""

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        last = messages[-1].content if messages else ""
        return LLMResponse(
            content=f"Test narrative: {last[:80]}",
            model="test-model",
            provider="test",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            structured={
                "summary": f"Test analysis for: {last[:120]}",
                "confidence": 0.62,
                "bullets": ["test"],
            },
        )

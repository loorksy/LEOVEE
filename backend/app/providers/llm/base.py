from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    structured: dict[str, Any] | None = None


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse: ...


def mock_structured_response(messages: list[LLMMessage]) -> dict[str, Any]:
    last = messages[-1].content if messages else ""
    return {
        "summary": f"Mock analysis for: {last[:120]}",
        "confidence": 0.62,
        "bullets": ["Structure aligned", "Volatility moderate", "Risk within limits"],
    }

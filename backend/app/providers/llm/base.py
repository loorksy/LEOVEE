from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMMessage:
    """One turn, in provider-neutral form.

    The tool fields are structure, not text. An earlier version serialised a
    tool result into `content` as JSON and gave it `role="tool"`, which no
    provider accepts: Anthropic's Messages API takes only user and assistant
    roles and wants `tool_result` content blocks, and OpenAI wants
    `tool_call_id` as a field rather than a substring of the body. Both rejected
    the second turn of every tool conversation with a malformed-request error,
    several layers from the loop that built it.

    Carrying the structure here and translating per provider is what keeps the
    loop from having to know either wire format.
    """

    role: str
    content: str
    #: Set on an assistant turn that asked for tools.
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    #: Set on a result turn, naming the call it answers.
    tool_call_id: str | None = None
    #: The tool's name, which Anthropic does not need and OpenAI does.
    tool_name: str | None = None


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    structured: dict[str, Any] | None = None
    tool_calls: list[LLMToolCall] = field(default_factory=list)


@dataclass
class LLMStreamChunk:
    text: str
    model: str
    provider: str
    done: bool = False
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> LLMResponse: ...

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]: ...

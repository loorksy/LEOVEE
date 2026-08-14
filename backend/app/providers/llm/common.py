"""Shared retry / timeout / error-normalization helpers for LLM providers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.providers.llm.base import LLMMessage
from app.providers.llm.errors import (
    LLMAuthError,
    LLMBadResponseError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.05


def normalize_provider_exception(exc: BaseException) -> LLMError:
    """Map SDK / HTTP exceptions into a stable LLMError taxonomy."""
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return LLMTimeoutError(str(exc) or "LLM request timed out")

    name = type(exc).__name__.lower()
    message = str(exc) or type(exc).__name__
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)

    lowered = message.lower()
    if status in {401, 403} or "auth" in name or "authentication" in lowered:
        return LLMAuthError(message)
    # OpenRouter / provider quota exhaustion — treat as retryable so free-model rotation continues.
    if (
        status in {402, 429}
        or "rate" in name
        or "rate_limit" in lowered
        or "quota" in lowered
        or "credit" in lowered
        or "insufficient" in lowered
        or "capacity" in lowered
        or "provider returned error" in lowered
    ):
        return LLMRateLimitError(message)
    if status is not None and int(status) >= 500:
        return LLMError(message, code="llm_upstream", retryable=True)
    if "timeout" in name or "timed out" in message.lower():
        return LLMTimeoutError(message)
    return LLMError(message, code="llm_error", retryable=False)


async def with_timeout_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> T:
    """Run an async LLM call with timeout and limited retries on retryable errors."""
    attempt = 0
    while True:
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — normalized below
            normalized = normalize_provider_exception(exc)
            if not normalized.retryable or attempt >= max_retries:
                raise normalized from exc
            await asyncio.sleep(backoff_seconds * (2**attempt))
            attempt += 1


def parse_structured_content(
    content: str,
    response_format: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not response_format:
        return None
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMBadResponseError("structured_output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMBadResponseError("structured_output must be a JSON object")
    return parsed


def usage_from_openai(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", prompt + completion) or (prompt + completion))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def usage_from_anthropic(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt = int(getattr(usage, "input_tokens", 0) or 0)
    completion = int(getattr(usage, "output_tokens", 0) or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "input_tokens": prompt,
        "output_tokens": completion,
    }


# --- tool-conversation translation -------------------------------------------
#
# The two providers disagree about how a tool exchange is represented, and the
# disagreement is structural rather than cosmetic. Putting the translation here
# means the tool loop builds one neutral conversation and neither it nor the
# synthesizer has to know which provider answered.


def to_openai_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """OpenAI: tool calls on the assistant turn, results as role="tool"."""
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.tool_call_id is not None:
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                }
            )
            continue
        entry: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
            # An assistant turn that only asked for tools has no prose, and
            # OpenAI rejects a null content alongside tool_calls.
            entry["content"] = message.content or ""
        out.append(entry)
    return out


def to_anthropic_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Anthropic: only user and assistant roles, with tool blocks inside content.

    A tool *result* is a **user** turn carrying `tool_result` blocks — which
    reads oddly until you notice that the model is the one being told something.
    Consecutive results merge into one user turn, because the API rejects two
    user turns in a row.
    """
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            continue

        if message.tool_call_id is not None:
            block = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue

        if message.tool_calls:
            content: list[dict[str, Any]] = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            content.extend(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
                for call in message.tool_calls
            )
            out.append({"role": "assistant", "content": content})
            continue

        out.append({"role": message.role, "content": message.content})
    return out


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the neutral tool shape into OpenAI's nested function form.

    The registry emits `{name, description, input_schema}` — Anthropic's shape,
    which OpenAI rejects: it wants `{"type": "function", "function": {"name",
    "description", "parameters"}}`. Passing the wrong one through produced a 400
    on the *first* tool-enabled call, and because a 400 classifies as
    non-retryable the decision stage returned `provider_bad_request` without
    ever attempting a repair. The tools looked wired and were not.

    Idempotent: an entry already in OpenAI form passes through, so translating
    twice does not corrupt it.
    """
    out: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function":
            out.append(tool)
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema") or tool.get("parameters") or {},
                },
            }
        )
    return out

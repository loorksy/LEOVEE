"""Shared retry / timeout / error-normalization helpers for LLM providers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

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

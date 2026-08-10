"""Normalized LLM provider errors."""

from __future__ import annotations

from app.core.errors import LeoveeError


class LLMError(LeoveeError):
    """Base LLM failure (normalized across providers)."""

    def __init__(self, message: str, *, code: str = "llm_error", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LLMTimeoutError(LLMError):
    def __init__(self, message: str = "LLM request timed out") -> None:
        super().__init__(message, code="llm_timeout", retryable=True)


class LLMRateLimitError(LLMError):
    def __init__(self, message: str = "LLM rate limit exceeded") -> None:
        super().__init__(message, code="llm_rate_limit", retryable=True)


class LLMAuthError(LLMError):
    def __init__(self, message: str = "LLM authentication failed") -> None:
        super().__init__(message, code="llm_auth", retryable=False)


class LLMBadResponseError(LLMError):
    def __init__(self, message: str = "LLM returned an unusable response") -> None:
        super().__init__(message, code="llm_bad_response", retryable=False)

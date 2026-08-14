import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.request_context import logging_context

# Token-shaped strings must never appear in log output.
_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_-]{40,}"),
    re.compile(r"(?i)oanda[_-]?api[_-]?token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_-]{40,}"),
    # Long opaque tokens adjacent to OANDA context words
    re.compile(r"(?i)oanda[^A-Za-z0-9_-]{0,24}[A-Za-z0-9_-]{40,}"),
    # Leovee's own API keys (lvk_ + 256-bit token).
    re.compile(r"lvk_[A-Za-z0-9_-]{20,}"),
    # JWTs (header.payload.signature) — the '.' separators mean the generic
    # opaque-token classes above never span a whole bearer JWT.
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
)


def redact_secrets(value: Any) -> Any:
    """Recursively redact token-shaped substrings from log event values."""
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    if isinstance(value, dict):
        return {k: redact_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(v) for v in value)
    return value


def _redact_event_dict(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        event_dict[key] = redact_secrets(event_dict[key])
    return event_dict


def _merge_request_context(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    for key, value in logging_context().items():
        event_dict.setdefault(key, value)
    return event_dict


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _merge_request_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_event_dict,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

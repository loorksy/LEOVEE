from __future__ import annotations

from typing import Any

from app.core.config import Settings


def init_sentry(settings: Settings) -> None:
    """Initialize Sentry when DSN is configured; no-op otherwise."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )


def capture_exception(exc: BaseException, **extra: Any) -> None:
    try:
        import sentry_sdk
    except ImportError:
        return
    with sentry_sdk.push_scope() as scope:
        for key, value in extra.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_exception(exc)


def capture_message(message: str, level: str = "info") -> None:
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.capture_message(message, level=level)

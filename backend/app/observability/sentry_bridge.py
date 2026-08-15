from __future__ import annotations

from typing import Any, Literal

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)

#: The levels sentry_sdk.capture_message accepts. Spelled out here rather than
#: imported from sentry_sdk, which is an optional dependency this module is
#: careful to import only inside functions.
SentryLevel = Literal["fatal", "critical", "error", "warning", "info", "debug"]


def init_sentry(settings: Settings) -> None:
    """Initialize Sentry when DSN is configured; no-op otherwise."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        # Loud, not silent: an operator who set SENTRY_DSN believes crashes are
        # captured. If the SDK is not in the image, say so rather than swallow
        # every future error report.
        logger.error(
            "sentry_dsn_set_but_sdk_missing",
            detail="SENTRY_DSN is configured but sentry-sdk is not installed; "
            "no errors will be reported. Add sentry-sdk to the image.",
        )
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        # Exception local variables can hold the OANDA token or the DSN; keep
        # them out of the event that leaves the process.
        include_local_variables=False,
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


def capture_message(message: str, level: SentryLevel = "info") -> None:
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.capture_message(message, level=level)

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.core.config import Settings
from app.observability import sentry_bridge


def test_init_sentry_noop_without_dsn() -> None:
    sentry_bridge.init_sentry(Settings(SENTRY_DSN=None))


def test_init_sentry_calls_sdk_when_configured() -> None:
    calls: dict[str, object] = {}

    def _init(**kwargs: object) -> None:
        calls.update(kwargs)

    fake = SimpleNamespace(init=_init)
    previous = sys.modules.get("sentry_sdk")
    sys.modules["sentry_sdk"] = fake  # type: ignore[assignment]
    try:
        sentry_bridge.init_sentry(
            Settings(
                SENTRY_DSN="https://example@sentry.invalid/1",
                ENVIRONMENT="staging",
            )
        )
        assert calls["dsn"] == "https://example@sentry.invalid/1"
        assert calls["send_default_pii"] is False
    finally:
        if previous is None:
            sys.modules.pop("sentry_sdk", None)
        else:
            sys.modules["sentry_sdk"] = previous

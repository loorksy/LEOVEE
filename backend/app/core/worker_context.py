from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.core.request_context import bind_request_id, get_request_id


def job_payload_with_request_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach current request_id to an Arq job payload when present."""
    rid = get_request_id()
    if rid is None:
        return payload
    enriched = dict(payload)
    enriched.setdefault("request_id", rid)
    return enriched


def bind_worker_request_context(payload: dict[str, Any]) -> None:
    request_id = payload.get("request_id")
    if isinstance(request_id, str) and request_id:
        bind_request_id(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)


async def run_with_request_context[T](
    payload: dict[str, Any],
    fn: Callable[[], Awaitable[T]],
) -> T:
    bind_worker_request_context(payload)
    return await fn()

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import bind_request_id, reset_context
from app.observability.http_metrics import record_http_request
from app.observability.prometheus import (
    http_request_duration_seconds,
    http_requests_total,
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        reset_context()
        bind_request_id(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - started

        # Label by the MATCHED route template, not the raw path: a hostile
        # crawler hitting /x1 /x2 /x3… would otherwise mint one metric series
        # (and one leaked dict entry) per URL and blow up the API's memory. A
        # matched route is already a bounded template; everything unmatched
        # collapses to one bucket, capping cardinality at the route count.
        route = request.scope.get("route")
        template = getattr(route, "path", None)
        path = template if template else "__unmatched__"

        record_http_request(
            method=request.method,
            path=path,
            status_code=response.status_code,
            duration_seconds=duration,
        )
        status_bucket = f"{response.status_code // 100}xx"
        http_requests_total.labels(request.method.upper(), path, status_bucket).inc()
        http_request_duration_seconds.labels(request.method.upper(), path).observe(duration)
        response.headers["X-Request-ID"] = request_id
        return response

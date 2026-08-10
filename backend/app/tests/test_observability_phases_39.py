from __future__ import annotations

import pytest

from app.core.request_context import get_request_id, reset_context
from app.core.worker_context import bind_worker_request_context, job_payload_with_request_context


def test_job_payload_includes_request_id() -> None:
    reset_context()
    from app.core.request_context import bind_request_id

    bind_request_id("req-abc")
    payload = job_payload_with_request_context({"outcome": "WIN"})
    assert payload["request_id"] == "req-abc"
    assert payload["outcome"] == "WIN"


def test_worker_binds_request_id_from_payload() -> None:
    reset_context()
    bind_worker_request_context({"request_id": "worker-req-1"})
    assert get_request_id() == "worker-req-1"


@pytest.mark.asyncio
async def test_http_request_id_header() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready", headers={"X-Request-ID": "client-req-99"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "client-req-99"


@pytest.mark.asyncio
async def test_metrics_endpoint_includes_http_counters() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/health/ready")
        metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "http_requests_total" in body
    assert "leovee_up" in body


@pytest.mark.asyncio
async def test_security_headers_on_api_responses() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in response.headers

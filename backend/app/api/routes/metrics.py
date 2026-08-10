from __future__ import annotations

from fastapi import APIRouter, Response

from app.observability.http_metrics import prometheus_text

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ImportError:
        body = prometheus_text()
        return Response(content=body, media_type="text/plain; version=0.0.4")

    generated = generate_latest()
    if isinstance(generated, str):
        generated = generated.encode()
    return Response(
        content=generated + prometheus_text().encode(),
        media_type=CONTENT_TYPE_LATEST,
    )

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.core.config import get_settings
from app.observability.http_metrics import prometheus_text

router = APIRouter(tags=["metrics"])


def _authorize_metrics(authorization: str | None) -> None:
    settings = get_settings()
    token = settings.metrics_bearer_token
    require_auth = settings.environment in {"staging", "production"} or bool(token)
    if not require_auth:
        return
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="METRICS_BEARER_TOKEN is required in this environment",
        )
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="metrics authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/metrics")
async def prometheus_metrics(
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _authorize_metrics(authorization)
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

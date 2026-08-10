from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ImportError:
        body = (
            "# HELP leovee_up Leovee API process is running\n# TYPE leovee_up gauge\nleovee_up 1\n"
        )
        return Response(content=body, media_type="text/plain; version=0.0.4")

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

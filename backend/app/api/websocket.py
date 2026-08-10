from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.infrastructure.database import get_session_factory
from app.services.auth_service import AuthError, get_user_for_access_token

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/v1/stream")
async def authenticated_ws(websocket: WebSocket, token: str | None = None) -> None:
    await websocket.accept()
    settings = get_settings()
    if not token:
        await websocket.send_json({"error": "missing_token"})
        await websocket.close(code=4401)
        return

    factory = get_session_factory()
    if factory is None:
        await websocket.send_json({"error": "database_unavailable"})
        await websocket.close(code=1011)
        return

    try:
        async with factory() as session:
            await get_user_for_access_token(session, settings, token)
    except AuthError:
        await websocket.send_json({"error": "unauthorized"})
        await websocket.close(code=4401)
        return

    claims = decode_access_token(settings, token)
    await websocket.send_json({"event": "connected", "user": claims["sub"]})
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"event": "echo", "data": data})
    except WebSocketDisconnect:
        return

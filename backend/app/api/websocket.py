from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.infrastructure.database import get_session_factory
from app.infrastructure.realtime import candle_broadcaster
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
    symbols_param = websocket.query_params.get("symbols", "EURUSD")
    symbols = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]
    queues = [candle_broadcaster.subscribe(symbol) for symbol in symbols]

    await websocket.send_json({"event": "connected", "user": claims["sub"], "symbols": symbols})
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                await websocket.send_json({"event": "echo", "data": data})
            except TimeoutError:
                pass

            for queue in queues:
                while not queue.empty():
                    payload = queue.get_nowait()
                    await websocket.send_json(payload)
    except WebSocketDisconnect:
        for symbol, queue in zip(symbols, queues, strict=True):
            candle_broadcaster.unsubscribe(symbol, queue)
        return

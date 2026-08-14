from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.core.symbols import DEFAULT_SYMBOL
from app.core.tenant import resolve_tenant_context, resolve_workspace_context
from app.infrastructure.database import get_session_factory
from app.infrastructure.realtime import (
    annotation_broadcaster,
    candle_broadcaster,
    notification_broadcaster,
)
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
    symbols_param = websocket.query_params.get("symbols", DEFAULT_SYMBOL)
    symbols = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]
    candle_queues = [candle_broadcaster.subscribe(symbol) for symbol in symbols]

    channels_param = websocket.query_params.get("channels", "candles")
    channels = {c.strip().lower() for c in channels_param.split(",") if c.strip()}
    annotation_queue = None
    workspace_key: str | None = None
    if "annotations" in channels:
        workspace_id_param = websocket.query_params.get("workspace_id")
        if not workspace_id_param:
            await websocket.send_json({"error": "workspace_id_required_for_annotations"})
            await websocket.close(code=4400)
            return
        try:
            async with factory() as session:
                user, _ = await get_user_for_access_token(session, settings, token)
                tenant = await resolve_tenant_context(session, user.id)
                tenant = await resolve_workspace_context(
                    session,
                    tenant,
                    client_workspace_id=uuid.UUID(workspace_id_param),
                )
                if tenant.workspace_id is None:
                    raise ValueError("workspace missing")
                workspace_key = str(tenant.workspace_id)
        except Exception:
            await websocket.send_json({"error": "workspace_unauthorized"})
            await websocket.close(code=4403)
            return
        annotation_queue = annotation_broadcaster.subscribe(workspace_key)

    notification_queue = None
    if "notifications" in channels:
        workspace_id_param = websocket.query_params.get("workspace_id")
        if not workspace_id_param:
            await websocket.send_json({"error": "workspace_id_required_for_notifications"})
            await websocket.close(code=4400)
            return
        try:
            async with factory() as session:
                user, _ = await get_user_for_access_token(session, settings, token)
                tenant = await resolve_tenant_context(session, user.id)
                tenant = await resolve_workspace_context(
                    session,
                    tenant,
                    client_workspace_id=uuid.UUID(workspace_id_param),
                )
                if tenant.workspace_id is None:
                    raise ValueError("workspace missing")
                workspace_key = workspace_key or str(tenant.workspace_id)
        except Exception:
            await websocket.send_json({"error": "workspace_unauthorized"})
            await websocket.close(code=4403)
            return
        notification_queue = notification_broadcaster.subscribe(workspace_key)

    await websocket.send_json(
        {
            "event": "connected",
            "user": claims["sub"],
            "symbols": symbols,
            "channels": sorted(channels),
            "workspace_id": workspace_key,
        }
    )
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                await websocket.send_json({"event": "echo", "data": data})
            except TimeoutError:
                pass

            if "candles" in channels or not channels:
                for queue in candle_queues:
                    while not queue.empty():
                        payload = queue.get_nowait()
                        await websocket.send_json(payload)
            if annotation_queue is not None and workspace_key is not None:
                while not annotation_queue.empty():
                    payload = annotation_queue.get_nowait()
                    await websocket.send_json(payload)
            if notification_queue is not None and workspace_key is not None:
                while not notification_queue.empty():
                    payload = notification_queue.get_nowait()
                    await websocket.send_json(payload)
    except WebSocketDisconnect:
        for symbol, queue in zip(symbols, candle_queues, strict=True):
            candle_broadcaster.unsubscribe(symbol, queue)
        if annotation_queue is not None and workspace_key is not None:
            annotation_broadcaster.unsubscribe(workspace_key, annotation_queue)
        if notification_queue is not None and workspace_key is not None:
            notification_broadcaster.unsubscribe(workspace_key, notification_queue)
        return

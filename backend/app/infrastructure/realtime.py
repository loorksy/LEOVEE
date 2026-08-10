from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from app.core.config import get_settings


class CandleBroadcaster:
    """Fan-out completed candles to WebSocket subscribers (Redis when configured)."""

    def __init__(self) -> None:
        self._local_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def subscribe(self, symbol: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._local_queues[symbol.upper()].append(queue)
        return queue

    def unsubscribe(self, symbol: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        symbol = symbol.upper()
        if queue in self._local_queues.get(symbol, []):
            self._local_queues[symbol].remove(queue)

    async def publish(self, symbol: str, payload: dict[str, Any]) -> None:
        symbol = symbol.upper()
        settings = get_settings()
        if settings.redis_url:
            try:
                import redis.asyncio as redis

                client = redis.from_url(settings.redis_url)
                await client.publish(f"candles:{symbol}", json.dumps(payload))
                await client.close()
            except Exception:
                pass

        for queue in list(self._local_queues.get(symbol, [])):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                continue


candle_broadcaster = CandleBroadcaster()


class WorkspaceEventBroadcaster:
    """Fan-out workspace-scoped chart annotation events to WebSocket subscribers."""

    def __init__(self) -> None:
        self._local_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def subscribe(self, workspace_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._local_queues[workspace_id].append(queue)
        return queue

    def unsubscribe(self, workspace_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._local_queues.get(workspace_id, []):
            self._local_queues[workspace_id].remove(queue)

    async def publish(self, workspace_id: str, payload: dict[str, Any]) -> None:
        settings = get_settings()
        if settings.redis_url:
            try:
                import redis.asyncio as redis

                client = redis.from_url(settings.redis_url)
                await client.publish(f"chart:{workspace_id}", json.dumps(payload))
                await client.close()
            except Exception:
                pass

        for queue in list(self._local_queues.get(workspace_id, [])):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                continue


annotation_broadcaster = WorkspaceEventBroadcaster()

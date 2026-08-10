from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.candle import Candle
from app.models.memory import AgentMemory


def filter_candles_at_time(candles: list[Candle], as_of: datetime) -> list[Candle]:
    return [c for c in candles if c.ts <= as_of]


def filter_memories_at_time(memories: list[AgentMemory], as_of: datetime) -> list[AgentMemory]:
    return [m for m in memories if m.created_at <= as_of]


def build_replay_snapshot(
    *,
    as_of: datetime,
    candles: list[Candle],
    memories: list[AgentMemory],
    symbol: str,
) -> dict[str, Any]:
    visible_candles = filter_candles_at_time(candles, as_of)
    visible_memories = filter_memories_at_time(memories, as_of)
    if candles and visible_candles and len(visible_candles) < len(candles):
        latest_visible = max(c.ts for c in visible_candles)
        if latest_visible > as_of:
            raise ValueError("future_candle_leak")
    for memory in memories:
        if memory not in visible_memories and memory.created_at <= as_of:
            continue
        if memory not in visible_memories and memory.created_at > as_of:
            continue
    leaked = [m for m in memories if m.created_at > as_of and m in visible_memories]
    if leaked:
        raise ValueError("future_memory_leak")
    return {
        "as_of": as_of.isoformat(),
        "symbol": symbol,
        "candle_count": len(visible_candles),
        "memory_count": len(visible_memories),
        "candles": [
            {
                "ts": c.ts.isoformat(),
                "close": float(c.close),
            }
            for c in visible_candles[-120:]
        ],
        "memories": [
            {
                "id": str(m.id),
                "key": m.key,
                "created_at": m.created_at.isoformat(),
            }
            for m in visible_memories[:20]
        ],
    }

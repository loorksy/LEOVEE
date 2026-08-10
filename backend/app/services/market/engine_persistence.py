from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_artifacts import MarketEvent, PriceZone, Structure


async def persist_engine_outputs(
    session: AsyncSession,
    *,
    symbol_id: uuid.UUID,
    timeframe: str,
    as_of: datetime,
    engines: dict[str, Any],
) -> dict[str, int]:
    """Persist deterministic engine snapshots for episodic memory / retrieval (Phase 11)."""
    counts = {"market_events": 0, "structures": 0, "price_zones": 0}
    ts = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)

    structure = engines.get("structure") or {}
    if structure:
        row = Structure(
            symbol_id=symbol_id,
            timeframe=timeframe,
            structure_type=str(structure.get("bias", "NEUTRAL")),
            start_ts=ts,
            geometry_json={
                "swing_high": structure.get("swing_high"),
                "swing_low": structure.get("swing_low"),
            },
            confidence=Decimal("0.6"),
        )
        session.add(row)
        counts["structures"] += 1

        session.add(
            MarketEvent(
                symbol_id=symbol_id,
                timeframe=timeframe,
                event_type="STRUCTURE_BIAS",
                ts=ts,
                price=Decimal(str(structure["swing_high"]))
                if structure.get("swing_high") is not None
                else None,
                confidence=Decimal("0.6"),
                evidence_json=structure,
            )
        )
        counts["market_events"] += 1

    volatility = engines.get("volatility") or {}
    if volatility:
        session.add(
            MarketEvent(
                symbol_id=symbol_id,
                timeframe=timeframe,
                event_type="VOLATILITY_REGIME",
                ts=ts,
                confidence=Decimal("0.5"),
                evidence_json=volatility,
            )
        )
        counts["market_events"] += 1

    liquidity = engines.get("liquidity") or {}
    for sweep in liquidity.get("sweeps") or []:
        session.add(
            MarketEvent(
                symbol_id=symbol_id,
                timeframe=timeframe,
                event_type="LIQUIDITY_SWEEP",
                ts=ts,
                strength=Decimal("0.7"),
                evidence_json={"sweep": sweep, **liquidity},
            )
        )
        counts["market_events"] += 1

    zones_payload = engines.get("zones") or {}
    for zone in zones_payload.get("zones") or []:
        session.add(
            PriceZone(
                symbol_id=symbol_id,
                timeframe=timeframe,
                zone_type=str(zone.get("type", "UNKNOWN")),
                price_low=Decimal(str(zone["low"])),
                price_high=Decimal(str(zone["high"])),
                start_ts=ts,
                strength=Decimal(str(zone.get("strength", 0.5))),
            )
        )
        counts["price_zones"] += 1

    await session.flush()
    return counts


async def list_market_events_for_symbol(
    session: AsyncSession,
    symbol_id: uuid.UUID,
    *,
    timeframe: str | None = None,
    limit: int = 100,
) -> list[MarketEvent]:
    stmt = select(MarketEvent).where(MarketEvent.symbol_id == symbol_id)
    if timeframe:
        stmt = stmt.where(MarketEvent.timeframe == timeframe)
    stmt = stmt.order_by(MarketEvent.ts.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.status import is_unavailable
from app.models.market_artifacts import MarketEvent, PriceZone, Structure


async def persist_engine_outputs(
    session: AsyncSession,
    *,
    symbol_id: uuid.UUID,
    timeframe: str,
    as_of: datetime,
    engines: dict[str, Any],
) -> dict[str, int]:
    """Persist deterministic engine snapshots for episodic memory / retrieval.

    **Only engines whose output is a market artifact are written here.** A
    structure, a zone, a pattern and a sweep describe the market and outlive the
    run that found them; `plan_sanity`, `risk`, `scenarios` and
    `timeframe_selection` describe *this run's reasoning* and belong to the
    agent trace, where they are written. The distinction is not cosmetic —
    storing run-scoped reasoning as a market artifact would let a later
    retrieval treat one run's opinion as an observed fact about the market.

    The omission is listed rather than implied: an engine that appears in
    neither list is a gap, and there is a conformance test that says so.
    """
    counts = {"market_events": 0, "structures": 0, "price_zones": 0}
    ts = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)

    # An engine that declined to answer has nothing to persist. Without this,
    # `structure.get("bias", "NEUTRAL")` would store a NEUTRAL structure row
    # derived from an "unavailable" payload — a fabricated artifact that later
    # reads (episodic memory, retrieval) could not tell apart from a measured
    # one.
    engines = {name: payload for name, payload in engines.items() if not is_unavailable(payload)}

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

    intelligence = engines.get("market_intelligence") or {}
    if intelligence:
        session.add(
            MarketEvent(
                symbol_id=symbol_id,
                timeframe=timeframe,
                event_type="MARKET_INTELLIGENCE",
                ts=ts,
                confidence=Decimal(str(intelligence.get("confidence", 0.5))),
                evidence_json=intelligence,
            )
        )
        counts["market_events"] += 1

    mtf = engines.get("mtf") or {}
    if mtf:
        session.add(
            MarketEvent(
                symbol_id=symbol_id,
                timeframe=timeframe,
                event_type="MTF_ALIGNMENT",
                ts=ts,
                confidence=Decimal("0.55"),
                evidence_json=mtf,
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

    # Chart patterns are market facts with a timestamp: they were there before
    # this run and will be there after it. Persisting them is what lets a later
    # analysis say "this level has been the neckline of a double top since
    # Tuesday" instead of rediscovering it every time.
    geometry = engines.get("geometry") or {}
    for pattern in geometry.get("patterns") or []:
        target = pattern.get("projected_target")
        session.add(
            MarketEvent(
                symbol_id=symbol_id,
                timeframe=timeframe,
                event_type=f"PATTERN_{str(pattern.get('pattern_type', 'UNKNOWN')).upper()}",
                ts=ts,
                price=Decimal(str(target)) if isinstance(target, int | float) else None,
                confidence=Decimal(str(pattern.get("confidence", 0))) / Decimal("100"),
                evidence_json={
                    "status": pattern.get("status"),
                    "stage": pattern.get("stage"),
                    "completion_ratio": pattern.get("completion_ratio"),
                    "break_direction": pattern.get("break_direction"),
                    "break_level": pattern.get("break_level"),
                    "evidence": pattern.get("evidence"),
                },
                invalidation_json={"break_level": pattern.get("break_level")},
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

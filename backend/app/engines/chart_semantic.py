from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.chart import (
    ChartAnchor,
    ChartGeometry,
    ChartSemanticModel,
    ChartSemanticOperation,
    ChartSemanticType,
    ChartStyle,
)


def _anchor(ts: datetime, price: float, timeframe: str | None = None) -> ChartAnchor:
    return ChartAnchor(ts=ts.isoformat(), price=float(price), timeframe=timeframe)


def build_chart_semantic_model(
    *,
    symbol: str,
    timeframe: str,
    as_of: datetime,
    engines: dict[str, Any],
) -> ChartSemanticModel:
    """Build renderer-agnostic chart operations from deterministic engine outputs."""
    operations: list[ChartSemanticOperation] = []

    zones = engines.get("zones", {}).get("zones", [])
    for zone in zones[:2]:
        low = zone.get("low")
        high = zone.get("high")
        if low is None or high is None:
            continue
        operations.append(
            ChartSemanticOperation(
                semantic_type=ChartSemanticType.DRAW_ZONE,
                geometry=ChartGeometry(
                    anchors=[
                        _anchor(as_of, float(low), timeframe),
                        _anchor(as_of, float(high), timeframe),
                    ],
                    metadata={"zone_type": zone.get("type", "ZONE")},
                ),
                style=ChartStyle(fill_opacity=0.15, label=str(zone.get("type", "ZONE"))),
            )
        )

    structure = engines.get("structure", {})
    swing_low = structure.get("swing_low")
    swing_high = structure.get("swing_high")
    if swing_low is not None and swing_high is not None:
        operations.append(
            ChartSemanticOperation(
                semantic_type=ChartSemanticType.DRAW_STRUCTURE,
                geometry=ChartGeometry(
                    anchors=[
                        _anchor(as_of, float(swing_low), timeframe),
                        _anchor(as_of, float(swing_high), timeframe),
                    ],
                    metadata={"bias": structure.get("bias"), "structure": structure.get("label")},
                ),
                style=ChartStyle(line_width=2, label=structure.get("label")),
            )
        )

    liquidity = engines.get("liquidity", {})
    pools = liquidity.get("pools") or liquidity.get("equal_levels") or []
    if isinstance(pools, list):
        for pool in pools[:1]:
            price = pool.get("price") if isinstance(pool, dict) else None
            if price is not None:
                operations.append(
                    ChartSemanticOperation(
                        semantic_type=ChartSemanticType.DRAW_LIQUIDITY,
                        geometry=ChartGeometry(
                            anchors=[_anchor(as_of, float(price), timeframe)],
                            metadata={"pool_type": pool.get("type", "liquidity")},
                        ),
                        style=ChartStyle(line_width=1, label="liquidity"),
                    )
                )

    risk = engines.get("risk", {})
    entry = risk.get("entry")
    stop = risk.get("stop")
    if entry is not None and stop is not None:
        operations.append(
            ChartSemanticOperation(
                semantic_type=ChartSemanticType.DRAW_SETUP,
                geometry=ChartGeometry(
                    anchors=[
                        _anchor(as_of, float(entry), timeframe),
                        _anchor(as_of, float(stop), timeframe),
                    ],
                    metadata={"direction": engines.get("decision", {}).get("direction")},
                ),
                style=ChartStyle(color="#3b82f6", label="setup"),
            )
        )

    decision = engines.get("decision", {})
    if decision.get("direction") in {"BUY", "SELL"} and swing_low is not None:
        operations.append(
            ChartSemanticOperation(
                semantic_type=ChartSemanticType.DRAW_LEVEL,
                geometry=ChartGeometry(
                    anchors=[_anchor(as_of, float(swing_low), timeframe)],
                    metadata={"level_type": "invalidation"},
                ),
                style=ChartStyle(color="#ef4444", label="invalidation"),
            )
        )

    return ChartSemanticModel(
        version=1,
        symbol=symbol,
        timeframe=timeframe,
        operations=operations,
    )

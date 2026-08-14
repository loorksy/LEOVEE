"""Everything the chart draws, from the engines that measured it.

One assembly point, so the picture and the narrative cannot disagree. A level
the text cites and a line the user sees come from the same engine output, at the
same price, with the same confidence — because both are built here.

Two defects this replaces, and both were invisible on screen:

**Every anchor carried the same timestamp.** `as_of` was used for all of them,
so a supply zone spanning four hours and a swing structure spanning two days
both rendered as vertical pairs at the right edge. The shapes were right, the
positions were meaningless, and nothing downstream could tell.

**Six semantic types stood in for twenty-four.** A neckline, a channel and a
demand zone all arrived as `DRAW_STRUCTURE`, leaving the renderer to guess the
tool from the anchor count.

Geometry now supplies its own annotations (`geometry/to_annotations.py`) with
real pivot timestamps; this module adds what geometry does not know about —
zones, liquidity, and the plan's own levels.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engines.geometry.to_annotations import geometry_to_annotations
from app.engines.geometry.types import GeometrySnapshot
from app.schemas.chart import (
    ChartAnchor,
    ChartGeometry,
    ChartSemanticModel,
    ChartSemanticOperation,
    ChartSemanticRole,
    ChartSemanticType,
    ChartStyle,
)

__all__ = ["build_chart_semantic_model"]

_ENTRY_COLOUR = "#3b82f6"
_STOP_COLOUR = "#ef4444"
_TARGET_COLOUR = "#22c55e"

#: How many of each kind reach the chart. The geometry engine caps its own
#: output; these are the ones it does not produce.
_MAX_ZONES = 3
_MAX_LIQUIDITY = 3


def _anchor(ts: datetime, price: float, timeframe: str | None = None) -> ChartAnchor:
    return ChartAnchor(ts=ts.isoformat(), price=float(price), timeframe=timeframe)


def _ts_of(value: Any, fallback: datetime) -> datetime:
    """A stored timestamp, or the moment of analysis when there is none.

    The fallback is named rather than silent: an annotation anchored at `as_of`
    is one whose real extent was not recorded, and a reader zooming out should
    see it sitting at the right edge rather than believe it spans the chart.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return fallback
    return fallback


def _zones(
    engines: dict[str, Any], *, as_of: datetime, timeframe: str
) -> list[ChartSemanticOperation]:
    zones = (engines.get("zones") or {}).get("zones") or []
    operations: list[ChartSemanticOperation] = []
    for zone in zones[:_MAX_ZONES]:
        if not isinstance(zone, dict):
            continue
        low, high = zone.get("low"), zone.get("high")
        if low is None or high is None:
            continue
        supply = str(zone.get("type", "")).upper().startswith("SUPPLY")
        start = _ts_of(zone.get("from_ts") or zone.get("created_ts"), as_of)
        end = _ts_of(zone.get("to_ts"), as_of)
        operations.append(
            ChartSemanticOperation(
                semantic_type=(
                    ChartSemanticType.SUPPLY_ZONE if supply else ChartSemanticType.DEMAND_ZONE
                ),
                role=(ChartSemanticRole.SUPPLY_ZONE if supply else ChartSemanticRole.DEMAND_ZONE),
                confidence=_as_confidence(zone.get("strength")),
                geometry=ChartGeometry(
                    # A zone is a rectangle: two corners, each with its own
                    # time. Anchoring both at `as_of` drew it as a line.
                    anchors=[
                        _anchor(start, float(low), timeframe),
                        _anchor(end, float(high), timeframe),
                    ],
                    metadata={
                        "zone_type": zone.get("type"),
                        "strength": zone.get("strength"),
                        "fresh": zone.get("fresh"),
                    },
                ),
                style=ChartStyle(
                    fill_opacity=0.15,
                    color=_STOP_COLOUR if supply else _TARGET_COLOUR,
                    label=str(zone.get("type", "")),
                ),
            )
        )
    return operations


def _liquidity(
    engines: dict[str, Any], *, as_of: datetime, timeframe: str
) -> list[ChartSemanticOperation]:
    liquidity = engines.get("liquidity") or {}
    operations: list[ChartSemanticOperation] = []
    for bucket in ("equal_highs", "equal_lows", "sweeps"):
        for item in (liquidity.get(bucket) or [])[:_MAX_LIQUIDITY]:
            if not isinstance(item, dict):
                continue
            price = item.get("price")
            if price is None:
                continue
            operations.append(
                ChartSemanticOperation(
                    semantic_type=ChartSemanticType.PRICE_LINE,
                    role=ChartSemanticRole.LIQUIDITY_SWEEP,
                    geometry=ChartGeometry(
                        anchors=[_anchor(_ts_of(item.get("ts"), as_of), float(price), timeframe)],
                        metadata={"pool": bucket, "touches": item.get("touches")},
                    ),
                    style=ChartStyle(line_width=1, line_style="dashed", label=bucket),
                )
            )
    return operations


def _plan(
    decision: dict[str, Any], *, as_of: datetime, timeframe: str
) -> list[ChartSemanticOperation]:
    """Entry, stop and targets — read from the *decision*, not from the risk engine.

    The risk engine prices whatever levels it is handed, including the geometric
    placeholder computed before the model replied. Drawing those would put a
    line on the chart at a price no published plan ever named.
    """
    levels = decision.get("levels")
    if not isinstance(levels, dict) or decision.get("degraded"):
        return []

    direction = decision.get("direction")
    if direction not in ("BUY", "SELL"):
        return []

    operations: list[ChartSemanticOperation] = []
    for price, role, colour, label in (
        (levels.get("entry"), ChartSemanticRole.ENTRY, _ENTRY_COLOUR, "entry"),
        (levels.get("stop"), ChartSemanticRole.STOP_LOSS, _STOP_COLOUR, "stop"),
    ):
        if isinstance(price, int | float):
            operations.append(
                ChartSemanticOperation(
                    semantic_type=ChartSemanticType.PRICE_LINE,
                    role=role,
                    geometry=ChartGeometry(
                        anchors=[_anchor(as_of, float(price), timeframe)],
                        metadata={"direction": direction},
                    ),
                    style=ChartStyle(color=colour, line_width=2, label=label),
                )
            )

    for index, target in enumerate(levels.get("targets") or [], start=1):
        if isinstance(target, int | float):
            operations.append(
                ChartSemanticOperation(
                    semantic_type=ChartSemanticType.PRICE_LINE,
                    role=ChartSemanticRole.TAKE_PROFIT,
                    geometry=ChartGeometry(
                        anchors=[_anchor(as_of, float(target), timeframe)],
                        metadata={"direction": direction, "index": index},
                    ),
                    style=ChartStyle(color=_TARGET_COLOUR, line_width=1, label=f"tp{index}"),
                )
            )
    return operations


def _as_confidence(value: Any) -> int | None:
    """A 0–1 strength as a 0–100 confidence, or nothing.

    None rather than a default: a zone with no measured strength drawn at full
    confidence looks exactly like one the engine was sure about.
    """
    if not isinstance(value, int | float):
        return None
    return int(round(float(value) * 100)) if value <= 1 else int(round(float(value)))


def build_chart_semantic_model(
    *,
    symbol: str,
    timeframe: str,
    as_of: datetime,
    engines: dict[str, Any],
    geometry: GeometrySnapshot | None = None,
    decision: dict[str, Any] | None = None,
) -> ChartSemanticModel:
    """Renderer-agnostic chart operations from the deterministic engine outputs."""
    operations: list[ChartSemanticOperation] = []
    if geometry is not None:
        operations.extend(geometry_to_annotations(geometry, timeframe=timeframe))
    operations.extend(_zones(engines, as_of=as_of, timeframe=timeframe))
    operations.extend(_liquidity(engines, as_of=as_of, timeframe=timeframe))
    if decision:
        operations.extend(_plan(decision, as_of=as_of, timeframe=timeframe))

    return ChartSemanticModel(
        version=2,
        symbol=symbol,
        timeframe=timeframe,
        operations=operations,
    )

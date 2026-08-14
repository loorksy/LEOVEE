"""The tool surface: read-only, gold-only, workspace-bound.

Three properties hold for every tool here, and each is a decision rather than an
accident:

**Read-only.** Nothing mutates state. Leovee analyses and recommends; it places
no orders and touches no broker (ADR 0005), so no tool needs write access and
none is granted it. A read-only surface cannot be talked into doing damage by a
prompt injected through news text or a chart annotation.

**Gold-only.** Symbol arguments go through the allowlist, which raises rather
than substituting gold. A model that asks about EURUSD has made a mistake, and
answering about a different market would be worse than an error.

**Workspace-bound.** Tools receive an already-bound session. Row-level security
is what actually scopes the data, so a tool cannot widen its own access by
passing a different workspace id — there is no such parameter to pass.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.symbols import DEFAULT_SYMBOL, require_instrument
from app.core.tenant import TenantContext
from app.core.timeframes import ACTIVE_TIMEFRAMES, ANALYSIS_WINDOW_BARS
from app.engines.bar import bars_from_candles
from app.engines.primitives.indicators import adx, atr, bollinger, macd, rsi
from app.engines.primitives.structure import detect_structure_levels, level_to_dict
from app.models.enums import Timeframe
from app.services import market_data

__all__ = ["ToolContext", "ToolSpec", "TOOLS", "tool_definitions", "dispatch_tool"]


@dataclass(slots=True)
class ToolContext:
    """Everything a tool may touch. Deliberately small.

    ``tenant`` is identity, not a filter: workspace-scoped tools require it so
    the session can be RLS-bound, but no handler ever receives a workspace id
    as an argument to filter by — row-level security is the only scoping, and a
    tool cannot widen its own access by passing a different id (there is no
    such parameter to pass).
    """

    session: AsyncSession
    symbol: str = DEFAULT_SYMBOL
    tenant: TenantContext | None = None


ToolHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]

#: "platform" tools read shared market facts (candles, engines, news) and work
#: without a workspace. "workspace" tools read tenant rows and refuse to run on
#: an unbound context rather than silently returning another scope's answer.
ToolScope = Literal["platform", "workspace"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    scope: ToolScope = "platform"


def _timeframe(arguments: dict[str, Any], default: Timeframe = Timeframe.M15) -> Timeframe:
    raw = arguments.get("timeframe")
    if raw is None:
        return default
    timeframe = Timeframe(str(raw).upper())
    if timeframe not in ACTIVE_TIMEFRAMES:
        raise ValueError(
            f"{timeframe.value} is not stored. Available: "
            f"{', '.join(tf.value for tf in ACTIVE_TIMEFRAMES)}"
        )
    return timeframe


def _count(arguments: dict[str, Any], default: int = 120) -> int:
    raw = int(arguments.get("count", default))
    # Bounded so a tool call cannot pull a year of M1 into a prompt.
    return max(10, min(raw, ANALYSIS_WINDOW_BARS))


async def _load_bars(context: ToolContext, arguments: dict[str, Any], count: int) -> list[Any]:
    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    symbol_row = await market_data.get_or_create_symbol(context.session, spec.symbol)
    candles = await market_data.load_recent_candles(
        context.session,
        symbol_row.id,
        timeframe=_timeframe(arguments),
        count=count,
    )
    return bars_from_candles(candles)


async def _get_candles(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    count = _count(arguments)
    bars = await _load_bars(context, arguments, count)
    return {
        "timeframe": _timeframe(arguments).value,
        "count": len(bars),
        "candles": [
            {
                "ts": bar.ts.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ],
    }


async def _get_indicators(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    bars = await _load_bars(context, arguments, ANALYSIS_WINDOW_BARS)
    closes = [bar.close for bar in bars]
    macd_result = macd(closes)
    band = bollinger(closes)
    return {
        "timeframe": _timeframe(arguments).value,
        "bars": len(bars),
        "rsi14": rsi(closes, 14),
        "atr14": atr(bars, 14),
        "adx14": adx(bars, 14),
        "macd": None
        if macd_result is None
        else {
            "macd": macd_result.macd,
            "signal": macd_result.signal,
            "histogram": macd_result.histogram,
        },
        "bollinger": None
        if band is None
        else {
            "upper": band.upper,
            "middle": band.middle,
            "lower": band.lower,
            "percent_b": band.percent_b,
            "width_pct": band.width_pct,
        },
    }


async def _get_structure(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    bars = await _load_bars(context, arguments, ANALYSIS_WINDOW_BARS)
    analysis = detect_structure_levels(bars)
    return {
        "timeframe": _timeframe(arguments).value,
        "structure": analysis.structure,
        "current_price": analysis.current_price,
        "nearest_support": analysis.nearest_support,
        "nearest_resistance": analysis.nearest_resistance,
        "supports": [level_to_dict(level) for level in analysis.supports],
        "resistances": [level_to_dict(level) for level in analysis.resistances],
    }


async def _get_chart_image(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Hand the agent the picture of what it is analysing.

    Drawn from the same candle rows every other tool returns, so the chart and
    the numbers can never disagree.
    """
    from app.services.chart.visual_evidence import collect_visual_evidence

    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    evidence = await collect_visual_evidence(
        context.session,
        symbol=spec.symbol,
        timeframe=_timeframe(arguments),
    )
    return evidence.as_payload()


async def _get_data_coverage(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """What history exists, so the agent can tell thin data from a quiet market."""
    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    symbol_row = await market_data.get_or_create_symbol(context.session, spec.symbol)
    coverage: dict[str, Any] = {}
    for timeframe in ACTIVE_TIMEFRAMES:
        candles = await market_data.load_recent_candles(
            context.session, symbol_row.id, timeframe=timeframe, count=1
        )
        oldest = await market_data.load_oldest_candle(
            context.session, symbol_row.id, timeframe=timeframe
        )
        coverage[timeframe.value] = {
            "latest": candles[-1].ts.isoformat() if candles else None,
            "earliest": oldest.ts.isoformat() if oldest else None,
        }
    return {"symbol": spec.symbol, "coverage": coverage}


_SYMBOL_PARAM = {
    "type": "string",
    "description": "Instrument. Only XAUUSD is available.",
}
_TIMEFRAME_PARAM = {
    "type": "string",
    "enum": [tf.value for tf in ACTIVE_TIMEFRAMES],
    "description": "M1/M5/M15 are decision frames; H1/H4 are context only.",
}

_MARKET_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_candles",
        description="Raw OHLC candles for a timeframe, oldest first.",
        parameters={
            "type": "object",
            "properties": {
                "symbol": _SYMBOL_PARAM,
                "timeframe": _TIMEFRAME_PARAM,
                "count": {"type": "integer", "description": "10–500 candles."},
            },
        },
        handler=_get_candles,
    ),
    ToolSpec(
        name="get_indicators",
        description="RSI, ATR, ADX, MACD and Bollinger bands for a timeframe.",
        parameters={
            "type": "object",
            "properties": {"symbol": _SYMBOL_PARAM, "timeframe": _TIMEFRAME_PARAM},
        },
        handler=_get_indicators,
    ),
    ToolSpec(
        name="get_structure",
        description="Swing structure, clustered support and resistance levels.",
        parameters={
            "type": "object",
            "properties": {"symbol": _SYMBOL_PARAM, "timeframe": _TIMEFRAME_PARAM},
        },
        handler=_get_structure,
    ),
    ToolSpec(
        name="get_chart_image",
        description=(
            "PNG charts of the analysed frame and the two above it, drawn "
            "from the same candles the other tools return."
        ),
        parameters={
            "type": "object",
            "properties": {"symbol": _SYMBOL_PARAM, "timeframe": _TIMEFRAME_PARAM},
        },
        handler=_get_chart_image,
    ),
    ToolSpec(
        name="get_data_coverage",
        description="Stored history range per timeframe.",
        parameters={
            "type": "object",
            "properties": {"symbol": _SYMBOL_PARAM},
        },
        handler=_get_data_coverage,
    ),
)


def _build_registry() -> dict[str, ToolSpec]:
    """Merge every module's contributions, refusing duplicate names.

    A silent overwrite here would mean two tools with the same name and
    different behaviour depending on import order — the exact class of bug the
    single-registry design exists to rule out.
    """
    from app.agents.tools import engine_tools, learning_tools, record_tools

    merged: dict[str, ToolSpec] = {}
    for spec in (
        *_MARKET_TOOLS,
        *engine_tools.TOOLS,
        *record_tools.TOOLS,
        *learning_tools.TOOLS,
    ):
        if spec.name in merged:
            raise RuntimeError(f"duplicate tool name: {spec.name}")
        merged[spec.name] = spec
    return merged


TOOLS: dict[str, ToolSpec] = _build_registry()


def tool_definitions() -> list[dict[str, Any]]:
    """Provider-shaped tool declarations."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.parameters,
        }
        for spec in TOOLS.values()
    ]


async def dispatch_tool(
    context: ToolContext, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Run one tool call.

    Errors come back as data rather than exceptions: a model that asked for an
    unavailable timeframe should be told so and allowed to correct itself, not
    have the whole analysis aborted.
    """
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": "unknown_tool", "detail": name, "available": sorted(TOOLS)}
    if spec.scope == "workspace" and context.tenant is None:
        # Refusing beats answering: a workspace read on an unbound session
        # would either error deep in RLS or, worse, appear to succeed empty.
        return {"error": "workspace_context_required", "detail": name}
    try:
        return await spec.handler(context, arguments or {})
    except Exception as exc:  # noqa: BLE001 — surfaced to the model, not raised
        return {"error": type(exc).__name__, "detail": str(exc)}

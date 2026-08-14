"""Engine read tools: what the deterministic engines say about the market now.

Platform-scoped — every handler reads shared candles (or shared news rows) and
computes engine output; no workspace rows are touched, so none of these refuse
an unbound context. The properties of the registry hold here too, and each is
inherited rather than re-decided:

**Read-only.** Every handler computes over stored candles or lists stored news.
Nothing is mutated, ordered, or sent anywhere.

**Gold-only.** Symbol arguments go through ``require_instrument``, which raises
rather than substituting — the dispatcher turns that into an error the model
can read and correct.

**Nothing is modelled from spread.** ``get_price_context`` reports
``observed_spread`` as ``None`` unless a live quote actually exists — and no
live quote reaches this path, so it is always ``None`` here. An invented cost
number that gates a decision was the exact failure ``plan_sanity`` was written
to remove, and this surface does not reintroduce it.

**Bounded output.** The engines bound their own snapshots (that is their
contract, not a performance measure), and ``get_news`` clamps its limit, so no
tool call can dump a table into a prompt.

The candle-loading helper deliberately mirrors ``registry._load_bars`` rather
than importing it: the registry's private helpers are not API, and a copy that
drifts shows up in review while a cross-module import of privates does not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.timeframe import select_decision_timeframe
from app.agents.tools.registry import ToolContext, ToolSpec
from app.core.symbols import require_instrument
from app.core.timeframes import (
    ACTIVE_TIMEFRAMES,
    ANALYSIS_WINDOW_BARS,
    DECISION_TIMEFRAMES,
    MTF_CONTEXT_STACK,
)
from app.engines.bar import OHLCBar, bars_from_candles
from app.engines.geometry import run_geometry_engine
from app.engines.liquidity import run_liquidity_engine
from app.engines.mtf import run_mtf_engine
from app.engines.plan_sanity import measure_price_context
from app.engines.volatility import run_volatility_engine
from app.engines.zones import run_zones_engine
from app.models.enums import Timeframe
from app.services import market_data
from app.services.market.calendar import (
    METAL_BREAK_HOUR_NY,
    METAL_SUNDAY_OPEN_HOUR_NY,
    WEEK_CLOSE_HOUR_NY,
    get_session_status,
)
from app.services.news_service import list_recent_news

__all__ = ["TOOLS"]

#: News output is bounded so a tool call cannot pull the whole table into a
#: prompt. The default matches the service's own; the cap is a hard ceiling.
NEWS_DEFAULT_LIMIT = 20
NEWS_MAX_LIMIT = 100


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


def _decision_timeframe(arguments: dict[str, Any]) -> Timeframe:
    """M1/M5/M15 only: a context frame cannot be the frame a scalp decides on."""
    raw = arguments.get("timeframe")
    if raw is None:
        return Timeframe.M15
    timeframe = Timeframe(str(raw).upper())
    if timeframe not in DECISION_TIMEFRAMES:
        raise ValueError(
            f"{timeframe.value} is not a decision timeframe. Available: "
            f"{', '.join(tf.value for tf in DECISION_TIMEFRAMES)}"
        )
    return timeframe


async def _load_bars(
    context: ToolContext,
    arguments: dict[str, Any],
    timeframe: Timeframe,
    count: int = ANALYSIS_WINDOW_BARS,
) -> list[OHLCBar]:
    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    symbol_row = await market_data.get_or_create_symbol(context.session, spec.symbol)
    candles = await market_data.load_recent_candles(
        context.session,
        symbol_row.id,
        timeframe=timeframe,
        count=count,
    )
    return bars_from_candles(candles)


async def _load_ladder(
    context: ToolContext,
    arguments: dict[str, Any],
    frames: tuple[Timeframe, ...],
) -> dict[str, list[OHLCBar]]:
    """Stored bars per frame, keyed by code — how the MTF engine is fed elsewhere."""
    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    symbol_row = await market_data.get_or_create_symbol(context.session, spec.symbol)
    ladder: dict[str, list[OHLCBar]] = {}
    for timeframe in frames:
        candles = await market_data.load_recent_candles(
            context.session,
            symbol_row.id,
            timeframe=timeframe,
            count=ANALYSIS_WINDOW_BARS,
        )
        ladder[timeframe.value] = bars_from_candles(candles)
    return ladder


async def _get_geometry(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """The M3 snapshot, bounded exactly as the engine bounds it."""
    timeframe = _timeframe(arguments)
    bars = await _load_bars(context, arguments, timeframe)
    return {"timeframe": timeframe.value, **run_geometry_engine(bars)}


async def _get_zones(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    timeframe = _timeframe(arguments)
    bars = await _load_bars(context, arguments, timeframe)
    return {"timeframe": timeframe.value, **run_zones_engine(bars)}


async def _get_liquidity(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    timeframe = _timeframe(arguments)
    bars = await _load_bars(context, arguments, timeframe)
    return {"timeframe": timeframe.value, **run_liquidity_engine(bars)}


async def _get_volatility_regime(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    timeframe = _timeframe(arguments)
    bars = await _load_bars(context, arguments, timeframe)
    return {"timeframe": timeframe.value, "bars": len(bars), **run_volatility_engine(bars)}


async def _get_mtf_bias(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """The H4/H1/M15 ladder read, fed the way the reevaluation sweep feeds it."""
    decision = _decision_timeframe(arguments)
    frames = tuple(dict.fromkeys((*MTF_CONTEXT_STACK, decision)))
    ladder = await _load_ladder(context, arguments, frames)
    return run_mtf_engine(ladder, decision_timeframe=decision.value)


async def _get_price_context(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Measured floor, never an assumed cost.

    ``observed_spread`` stays ``None``: no live quote exists on this path, and
    inventing one would put a fabricated cost in front of a decision (D12).
    """
    timeframe = _timeframe(arguments)
    bars = await _load_bars(context, arguments, timeframe)
    volatility = run_volatility_engine(bars)
    measured = measure_price_context(
        bars,
        atr=float(volatility.get("atr") or 0.0),
        observed_spread=None,
    )
    return {"timeframe": timeframe.value, "usable": measured.usable, **measured.to_dict()}


async def _get_timeframe_read(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """The frame the agent would choose right now, with every frame's reasons.

    The leading bias comes from the same MTF read the orchestrator uses, so
    this tool answers with the selection the pipeline would actually make —
    not a variant of it. When no frame is viable the selector raises, and the
    dispatcher hands the model the per-frame exclusions as error data.
    """
    frames = tuple(dict.fromkeys((*MTF_CONTEXT_STACK, *DECISION_TIMEFRAMES)))
    ladder = await _load_ladder(context, arguments, frames)
    mtf = run_mtf_engine(ladder)
    leading_bias = mtf.get("trade_bias")
    choice = select_decision_timeframe(ladder, leading_bias=leading_bias)
    return {"leading_bias": leading_bias, **choice.to_dict()}


async def _get_session_status(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Open or closed right now, plus the calendar facts the answer rests on."""
    spec = require_instrument(str(arguments.get("symbol", context.symbol)))
    moment = datetime.now(UTC)
    status = get_session_status(spec.symbol, moment)
    return {
        "symbol": spec.symbol,
        "checked_at": moment.isoformat(),
        "is_open": status.is_open,
        "reason": status.reason,
        "week": {
            "opens": f"Sunday {METAL_SUNDAY_OPEN_HOUR_NY}:00 America/New_York",
            "closes": f"Friday {WEEK_CLOSE_HOUR_NY}:00 America/New_York",
        },
        # The daily halt: [17:00, 18:00) New York, Monday-Thursday.
        "daily_halt": {
            "timezone": "America/New_York",
            "start_hour": METAL_BREAK_HOUR_NY,
            "end_hour": METAL_BREAK_HOUR_NY + 1,
            "days": "Monday-Thursday",
        },
    }


async def _get_news(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Recent stored news, newest first, bounded.

    ``news_events`` is deliberately platform-global (shared market fact, see the
    RLS coverage exemptions), so this tool is platform-scoped like the rest.
    """
    limit = max(1, min(int(arguments.get("limit", NEWS_DEFAULT_LIMIT)), NEWS_MAX_LIMIT))
    raw_currency = arguments.get("currency")
    rows = await list_recent_news(
        context.session,
        currency=str(raw_currency) if raw_currency else None,
        limit=limit,
    )
    return {
        "count": len(rows),
        "items": [
            {
                "published_at": row.published_at.isoformat(),
                "headline": row.headline,
                "summary": row.summary,
                "currency": row.currency,
                "market_impact": row.market_impact,
                "relevance": float(row.relevance) if row.relevance is not None else None,
                "source": row.source,
                "url": row.url,
            }
            for row in rows
        ],
    }


_SYMBOL_PARAM: dict[str, Any] = {
    "type": "string",
    "description": "Instrument. Only XAUUSD is available.",
}
_TIMEFRAME_PARAM: dict[str, Any] = {
    "type": "string",
    "enum": [tf.value for tf in ACTIVE_TIMEFRAMES],
    "description": "M1/M5/M15 are decision frames; H1/H4 are context only. Defaults to M15.",
}
_DECISION_TIMEFRAME_PARAM: dict[str, Any] = {
    "type": "string",
    "enum": [tf.value for tf in DECISION_TIMEFRAMES],
    "description": "Decision frame to weigh against the H4/H1/M15 ladder. Defaults to M15.",
}

_SYMBOL_AND_TIMEFRAME: dict[str, Any] = {
    "type": "object",
    "properties": {"symbol": _SYMBOL_PARAM, "timeframe": _TIMEFRAME_PARAM},
}

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_geometry",
        description=(
            "Deterministic chart geometry for a timeframe: trendlines, channels and up to "
            "three patterns with status and stage, plus pivots and candlestick signals."
        ),
        parameters=_SYMBOL_AND_TIMEFRAME,
        handler=_get_geometry,
    ),
    ToolSpec(
        name="get_zones",
        description=(
            "Supply and demand zones from unconsumed imbalances, scored on impulse, "
            "revisits and freshness, at most three per side."
        ),
        parameters=_SYMBOL_AND_TIMEFRAME,
        handler=_get_zones,
    ),
    ToolSpec(
        name="get_liquidity",
        description=(
            "Liquidity sweeps (a raid through a prior extreme that closes back inside) "
            "and equal-high/equal-low clusters where resting orders sit."
        ),
        parameters=_SYMBOL_AND_TIMEFRAME,
        handler=_get_liquidity,
    ),
    ToolSpec(
        name="get_volatility_regime",
        description="ATR and the volatility regime classification for a timeframe.",
        parameters=_SYMBOL_AND_TIMEFRAME,
        handler=_get_volatility_regime,
    ),
    ToolSpec(
        name="get_mtf_bias",
        description=(
            "Bias per frame across the H4/H1/M15 context ladder: alignment, conflict, "
            "which frame leads, which give context and which times the entry."
        ),
        parameters={
            "type": "object",
            "properties": {"symbol": _SYMBOL_PARAM, "timeframe": _DECISION_TIMEFRAME_PARAM},
        },
        handler=_get_mtf_bias,
    ),
    ToolSpec(
        name="get_price_context",
        description=(
            "Measured price context for a timeframe: noise floor (median wick), ATR and "
            "bars measured; observed_spread is null unless a live quote existed."
        ),
        parameters=_SYMBOL_AND_TIMEFRAME,
        handler=_get_price_context,
    ),
    ToolSpec(
        name="get_timeframe_read",
        description=(
            "Which scalping frame (M1/M5/M15) the agent would choose right now, with each "
            "frame's score, reasons and exclusion cause."
        ),
        parameters={"type": "object", "properties": {"symbol": _SYMBOL_PARAM}},
        handler=_get_timeframe_read,
    ),
    ToolSpec(
        name="get_session_status",
        description=(
            "Whether the gold market is open right now, with the weekly open/close and "
            "the daily halt window in New York time."
        ),
        parameters={"type": "object", "properties": {"symbol": _SYMBOL_PARAM}},
        handler=_get_session_status,
    ),
    ToolSpec(
        name="get_news",
        description=(
            "Recent stored market news, newest first, at most 100 items; optionally "
            "filtered by currency code."
        ),
        parameters={
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "description": "Filter to one currency code, e.g. USD.",
                },
                "limit": {
                    "type": "integer",
                    "description": "1-100 items, default 20.",
                },
            },
        },
        handler=_get_news,
    ),
)

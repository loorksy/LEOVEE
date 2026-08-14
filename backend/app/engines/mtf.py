"""Multi-timeframe alignment — and, when frames disagree, which one leads.

Real, as of M4. The placeholder read a ``trend`` string out of whatever another
engine had already put in a dict and counted votes over it, on a D1/H4/H1 stack
that belonged to a swing trader. Under D11 this platform scalps: the decision
lives on M1, M5 or M15, and H4/H1 are context that is *never* traded.

**Bias is measured here, once, from the bars.** Reading it out of another
engine's output made this a vote-counter over someone else's opinion — if that
engine's vocabulary drifted, the alignment silently drifted with it and nothing
compared the two.

**Disagreement is not averaged away.** Vote counting produces "mixed bullish"
for a market where H4 is falling and M15 is bouncing, which is a description of
the arithmetic rather than of the market. The constitution requires the answer
to name which frame *leads* the decision, which gives *context*, and which
*times* the entry — so those three roles are assigned explicitly, and a genuine
conflict is reported as a conflict rather than resolved by majority.

A scalp taken against a strong higher-timeframe trend is a specific, common and
expensive mistake: the pullback you are selling is the trend's entry.
"""

from __future__ import annotations

from typing import Any

from app.core.timeframes import (
    DEFAULT_SERIES_TIMEFRAME,
    MTF_CONTEXT_STACK_CODES,
)
from app.engines.bar import OHLCBar
from app.engines.primitives.regime import detect_market_regime
from app.engines.primitives.structure import detect_structure_levels
from app.engines.status import INSUFFICIENT_DATA, engine_unavailable

__all__ = ["run_mtf_engine", "default_mtf_stack", "BIAS_BY_SHAPE"]

BIAS_BY_SHAPE: dict[str, str] = {
    "uptrend": "BULLISH",
    "downtrend": "BEARISH",
    "range": "NEUTRAL",
    "unknown": "UNKNOWN",
}

#: Below this, a frame has too few bars to have a structure worth comparing.
#: Deliberately lower than the analysis floor: a context frame is allowed to be
#: thinner than the frame being traded, and reporting it as UNKNOWN is more
#: useful than dropping it.
MIN_BARS_PER_FRAME = 30

_DIRECTIONAL = ("BULLISH", "BEARISH")


def default_mtf_stack() -> tuple[str, ...]:
    """The context ladder, slowest first. H4 → H1 → M15 under D11."""
    return MTF_CONTEXT_STACK_CODES


def _frame_bias(bars: list[OHLCBar]) -> dict[str, Any]:
    if len(bars) < MIN_BARS_PER_FRAME:
        return {"bias": "UNKNOWN", "shape": "unknown", "regime": None, "bars": len(bars)}
    analysis = detect_structure_levels(bars)
    regime = detect_market_regime(bars)
    return {
        "bias": BIAS_BY_SHAPE[analysis.structure],
        "shape": analysis.structure,
        "regime": regime.regime if regime.is_known else None,
        # A trending regime makes a structural bias worth more; a volatility
        # blowout makes it worth less, whatever the swings say.
        "trending": regime.trending,
        "bars": len(bars),
    }


def run_mtf_engine(
    bars_by_timeframe: dict[str, list[OHLCBar]],
    *,
    decision_timeframe: str = DEFAULT_SERIES_TIMEFRAME.value,
    stack: tuple[str, ...] = MTF_CONTEXT_STACK_CODES,
) -> dict[str, Any]:
    """Bias per frame, the alignment between them, and the three roles."""
    if not bars_by_timeframe:
        return engine_unavailable("mtf", INSUFFICIENT_DATA)

    frames = {tf: _frame_bias(bars_by_timeframe.get(tf) or []) for tf in stack}
    if decision_timeframe not in frames:
        frames[decision_timeframe] = _frame_bias(bars_by_timeframe.get(decision_timeframe) or [])

    if all(frame["bias"] == "UNKNOWN" for frame in frames.values()):
        # Nothing readable on any frame is a data problem, not a neutral market.
        return engine_unavailable("mtf", INSUFFICIENT_DATA, detail="NO_READABLE_FRAME")

    biases = {tf: str(frame["bias"]) for tf, frame in frames.items()}
    context_biases = [biases[tf] for tf in stack if tf in biases]
    bullish = context_biases.count("BULLISH")
    bearish = context_biases.count("BEARISH")

    # The leader is the slowest frame that actually says something. Slowest
    # first is not a preference for slow frames — it is what "context" means.
    leading_timeframe: str | None = None
    for tf in stack:
        if biases.get(tf) in _DIRECTIONAL:
            leading_timeframe = tf
            break
    leading_bias = biases.get(leading_timeframe or "", "NEUTRAL")

    decision_bias = biases.get(decision_timeframe, "UNKNOWN")
    conflict = (
        decision_bias in _DIRECTIONAL
        and leading_bias in _DIRECTIONAL
        and decision_bias != leading_bias
    )

    directional = [b for b in context_biases if b in _DIRECTIONAL]
    if directional and bullish == len(directional) and bearish == 0:
        alignment = "FULL_BULLISH"
    elif directional and bearish == len(directional) and bullish == 0:
        alignment = "FULL_BEARISH"
    elif bullish > bearish:
        alignment = "MIXED_BULLISH"
    elif bearish > bullish:
        alignment = "MIXED_BEARISH"
    else:
        alignment = "NEUTRAL"

    # The trade bias follows the leading context frame, not the vote. A majority
    # of fast frames does not overrule the structure they are moving inside.
    trade_bias = leading_bias if leading_bias in _DIRECTIONAL else "NEUTRAL"

    return {
        "stack": list(stack),
        "decision_timeframe": decision_timeframe,
        "biases": biases,
        "frames": frames,
        "alignment": alignment,
        "trade_bias": trade_bias,
        "conflict": conflict,
        # The three roles the constitution requires every answer to name.
        "roles": {
            "leads": leading_timeframe,
            "context": [tf for tf in stack if tf != leading_timeframe],
            "times_entry": decision_timeframe,
        },
        "htf": biases.get(stack[0], "UNKNOWN"),
        "ltf": decision_bias,
    }

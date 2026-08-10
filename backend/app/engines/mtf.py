from __future__ import annotations

from typing import Any

from app.models.enums import Timeframe


def _bias_from_trend(trend: str) -> str:
    if trend in ("UP", "BULLISH"):
        return "BULLISH"
    if trend in ("DOWN", "BEARISH"):
        return "BEARISH"
    return "NEUTRAL"


def run_mtf_engine(
    intelligence_by_tf: dict[str, dict[str, Any]],
    *,
    stack: tuple[str, ...] = ("D1", "H4", "H1"),
) -> dict[str, Any]:
    """
    HTF → LTF bias alignment pipeline (Phase 10).
    """
    biases: dict[str, str] = {}
    for tf in stack:
        intel = intelligence_by_tf.get(tf) or {}
        biases[tf] = _bias_from_trend(str(intel.get("trend", "UNKNOWN")))

    ordered = [biases.get(tf, "NEUTRAL") for tf in stack]
    bullish = sum(1 for b in ordered if b == "BULLISH")
    bearish = sum(1 for b in ordered if b == "BEARISH")

    if bullish == len(stack):
        alignment = "FULL_BULLISH"
        trade_bias = "BULLISH"
    elif bearish == len(stack):
        alignment = "FULL_BEARISH"
        trade_bias = "BEARISH"
    elif bullish > bearish:
        alignment = "MIXED_BULLISH"
        trade_bias = "BULLISH"
    elif bearish > bullish:
        alignment = "MIXED_BEARISH"
        trade_bias = "BEARISH"
    else:
        alignment = "NEUTRAL"
        trade_bias = "NEUTRAL"

    return {
        "stack": list(stack),
        "biases": biases,
        "alignment": alignment,
        "trade_bias": trade_bias,
        "htf": biases.get(stack[0], "NEUTRAL"),
        "ltf": biases.get(stack[-1], "NEUTRAL"),
    }


def default_mtf_stack() -> tuple[str, ...]:
    return (Timeframe.D1.value, Timeframe.H4.value, Timeframe.H1.value)

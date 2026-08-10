from __future__ import annotations

from typing import Any

from app.models.enums import RecommendationDirection, RecommendationStatus


def run_devils_advocate(
    *,
    decision: dict[str, Any],
    engines: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic adversarial gate (Phase 18). Fails closed on contradiction / weak edge.
    """
    direction = decision.get("direction")
    mtf = engines.get("mtf") or {}
    intelligence = engines.get("market_intelligence") or {}

    issues: list[str] = []
    if direction == RecommendationDirection.BUY.value and mtf.get("trade_bias") == "BEARISH":
        issues.append("decision_buy_vs_mtf_bearish")
    if direction == RecommendationDirection.SELL.value and mtf.get("trade_bias") == "BULLISH":
        issues.append("decision_sell_vs_mtf_bullish")
    if intelligence.get("exhaustion"):
        issues.append("exhaustion_flag")
    if float(decision.get("confidence", 0)) < 0.45:
        issues.append("low_confidence")

    approved = len(issues) == 0
    return {
        "approved": approved,
        "issues": issues,
        "severity": "HIGH" if not approved else "LOW",
    }


def run_reasoning_engine(
    *,
    symbol: str,
    decision: dict[str, Any],
    engines: dict[str, Any],
    adversarial: dict[str, Any],
) -> dict[str, Any]:
    """Structured reasoning output (Phase 18) — no chain-of-thought stored."""
    approved = adversarial.get("approved", False)
    status = RecommendationStatus.READY if approved else RecommendationStatus.FORMING
    if decision.get("direction") == RecommendationDirection.NO_TRADE.value:
        status = RecommendationStatus.INVALIDATED

    return {
        "approved": approved,
        "status": status.value,
        "summary": f"{symbol} {decision.get('direction')} reasoning",
        "adversarial": adversarial,
        "evidence_refs": {
            "mtf": engines.get("mtf"),
            "market_intelligence": engines.get("market_intelligence"),
        },
    }

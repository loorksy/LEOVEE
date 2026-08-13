from __future__ import annotations

from typing import Any

from app.models.enums import RecommendationDirection


def run_decision_engine(
    scenarios: dict[str, Any],
    risk: dict[str, Any],
) -> dict[str, Any]:
    if not risk.get("approved", False):
        return {
            "direction": RecommendationDirection.NO_TRADE.value,
            "confidence": 0.0,
            "rationale": risk.get("reason", "risk_rejected"),
        }
    candidates = scenarios.get("scenarios") or []
    if not candidates:
        # No scenarios means no analytical basis. Raising here would turn a
        # missing input into a 500; the analysis path fails closed instead.
        return {
            "direction": RecommendationDirection.NO_TRADE.value,
            "confidence": None,
            "rationale": "no_scenarios",
        }
    best = max(candidates, key=lambda s: s.get("confidence", 0))
    label = best.get("label", "NO_TRADE")
    direction_map = {
        "BULLISH": RecommendationDirection.BUY.value,
        "BEARISH": RecommendationDirection.SELL.value,
        "NO_TRADE": RecommendationDirection.NO_TRADE.value,
    }
    return {
        "direction": direction_map.get(label, RecommendationDirection.WAIT.value),
        "confidence": best.get("confidence", 0.0),
        "rationale": f"scenario_{label.lower()}",
        "scenario": best,
    }

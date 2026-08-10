from __future__ import annotations

from typing import Any

from app.models.enums import RecommendationDirection, RecommendationStatus
from app.services.analysis_service import map_decision_to_recommendation_status


def run_reasoning_baseline(
    *,
    symbol: str,
    decision: dict[str, Any],
    engines: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic reasoning step for baseline E2E (Phase 18 replaces with LLM + adversarial).
    """
    direction = decision.get("direction", RecommendationDirection.WAIT.value)
    confidence = float(decision.get("confidence", 0.0))
    structure_bias = (engines.get("structure") or {}).get("bias", "NEUTRAL")

    approved = direction not in (
        RecommendationDirection.NO_TRADE.value,
        RecommendationDirection.WAIT.value,
    )
    if approved and confidence < 0.35:
        approved = False

    status = map_decision_to_recommendation_status(decision)
    if not approved:
        status = RecommendationStatus.FORMING

    return {
        "approved": approved,
        "status": status.value,
        "summary": f"{symbol} {direction} aligned with structure {structure_bias}",
        "confidence": confidence,
        "adversarial": {"skipped": True, "reason": "baseline_deterministic"},
        "evidence_refs": {
            "structure": engines.get("structure"),
            "volatility": engines.get("volatility"),
        },
    }

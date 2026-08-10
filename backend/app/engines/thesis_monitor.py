from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.enums import RecommendationDirection, ThesisStatus


def evaluate_thesis_monitor(
    *,
    thesis_status: str,
    direction: str,
    last_price: Decimal,
    structure: dict[str, Any],
    invalidation: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic thesis monitor (Phase 22).
    Returns transition proposal or no-op.
    """
    if thesis_status in (
        ThesisStatus.INVALIDATED.value,
        ThesisStatus.TARGET_REACHED.value,
        ThesisStatus.EXPIRED.value,
    ):
        return {"action": "NONE"}

    swing_low = invalidation.get("swing_low") or structure.get("swing_low")
    swing_high = invalidation.get("swing_high") or structure.get("swing_high")
    target = invalidation.get("target_price")

    if (
        direction == RecommendationDirection.BUY.value
        and swing_low is not None
        and last_price < Decimal(str(swing_low))
    ):
        return {
            "action": "TRANSITION",
            "new_status": ThesisStatus.INVALIDATED.value,
            "event_type": "THESIS_INVALIDATED",
            "reason": "structure_break_below_swing_low",
        }

    if (
        direction == RecommendationDirection.SELL.value
        and swing_high is not None
        and last_price > Decimal(str(swing_high))
    ):
        return {
            "action": "TRANSITION",
            "new_status": ThesisStatus.INVALIDATED.value,
            "event_type": "THESIS_INVALIDATED",
            "reason": "structure_break_above_swing_high",
        }

    if target is not None:
        target_dec = Decimal(str(target))
        if direction == RecommendationDirection.BUY.value and last_price >= target_dec:
            return {
                "action": "TRANSITION",
                "new_status": ThesisStatus.TARGET_REACHED.value,
                "event_type": "TARGET_REACHED",
                "reason": "price_at_target",
            }
        if direction == RecommendationDirection.SELL.value and last_price <= target_dec:
            return {
                "action": "TRANSITION",
                "new_status": ThesisStatus.TARGET_REACHED.value,
                "event_type": "TARGET_REACHED",
                "reason": "price_at_target",
            }

    return {"action": "NONE"}

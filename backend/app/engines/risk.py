from __future__ import annotations

from decimal import Decimal
from typing import Any


def run_risk_engine(
    *,
    entry: Decimal,
    stop: Decimal,
    account_risk_pct: Decimal = Decimal("1"),
    pip_size: Decimal = Decimal("0.0001"),
    spread_pips: Decimal = Decimal("1.5"),
) -> dict[str, Any]:
    risk_distance = abs(entry - stop)
    if risk_distance <= 0:
        return {
            "approved": False,
            "decision": "NO_TRADE",
            "reason": "invalid_stop",
            "position_size_units": None,
        }
    spread_cost = spread_pips * pip_size
    adjusted_risk = risk_distance + spread_cost
    if adjusted_risk > risk_distance * Decimal("3"):
        return {
            "approved": False,
            "decision": "NO_TRADE",
            "reason": "spread_too_wide",
            "position_size_units": None,
        }
    notional_risk = account_risk_pct / Decimal("100")
    units = notional_risk / adjusted_risk
    return {
        "approved": True,
        "decision": "TRADE",
        "reason": None,
        "position_size_units": float(units),
        "risk_pips": float(risk_distance / pip_size),
    }

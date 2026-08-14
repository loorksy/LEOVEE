"""Position risk: distance, cost and size — for the instrument actually traded.

Two defects this replaces, both silent and both found by review rather than by
anything failing.

**The pip size was hardcoded to 0.0001**, a currency-pair convention, on a
platform that trades only gold. Gold prices to two decimals, so every
``risk_pips`` figure was a hundred times too large — and it looked like a
plausible number, sitting in the same payload as ``plan_sanity``'s correct one,
with nothing to say which was which.

**The stop was assumed to be below the entry.** A short plan has its stop above,
and a signed subtraction produces a negative distance that reads as an invalid
stop. The distance is now signed by the plan's own direction, which is derived
from the levels rather than passed in — the levels are the authority, and a
direction argument that disagreed with them would just be a second thing to
keep in step.

**No spread is modelled here.** A default of thirty gold pips inflated every
risk distance and, past a threshold, refused the plan outright with
``spread_too_wide`` — a rejection produced entirely by a constant nobody had
measured, on a platform with no broker and no order to fill. Sizing is now the
plan's own risk distance, which is a fact about the plan. Whether the live tape
leaves that stop any room is asked in ``plan_sanity``, against the candles.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.symbols import DEFAULT_SYMBOL, pip_size

__all__ = ["run_risk_engine"]


def run_risk_engine(
    *,
    entry: Decimal,
    stop: Decimal,
    targets: list[Decimal] | None = None,
    account_risk_pct: Decimal = Decimal("1"),
    symbol: str = DEFAULT_SYMBOL,
) -> dict[str, Any]:
    size = Decimal(str(pip_size(symbol) or 0.01))
    risk_distance = abs(entry - stop)
    if risk_distance <= 0:
        return {
            "approved": False,
            "decision": "NO_TRADE",
            "reason": "invalid_stop",
            "position_size_units": None,
            "direction": None,
        }

    # Read off the levels rather than taken as an argument: the levels are the
    # authority, and a direction that could disagree with them is one more thing
    # to keep in step for no gain.
    direction = "SELL" if stop > entry else "BUY"

    units = (account_risk_pct / Decimal("100")) / risk_distance
    reward_risk: float | None = None
    if targets:
        first = targets[0]
        reward = abs(first - entry)
        # A target on the stop's side of entry is a sign error, not an
        # unambitious plan, and a negative ratio downstream reads as a very
        # confident bad trade.
        if (direction == "BUY" and first > entry) or (direction == "SELL" and first < entry):
            reward_risk = float(reward / risk_distance)

    return {
        "approved": True,
        "decision": "TRADE",
        "reason": None,
        "direction": direction,
        "position_size_units": float(units),
        "risk_distance": float(risk_distance),
        "risk_pips": float(risk_distance / size),
        "reward_risk": reward_risk,
        "pip_size": float(size),
    }

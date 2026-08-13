from __future__ import annotations

from typing import Any

from app.engines.status import engine_unavailable


def run_scenario_engine(
    structure: dict[str, Any],
    volatility: dict[str, Any],
    liquidity: dict[str, Any],
) -> dict[str, Any]:
    """Scenario generation — not implemented yet (M4).

    The previous stub assigned confidences of 0.55 / 0.35 / 0.4 / 0.2 by hand
    and passed them straight through ``run_decision_engine`` into the number the
    user reads as the agent\'s confidence. A hand-picked constant presented as a
    measured probability is the single most misleading thing this pipeline could
    emit, so the engine now declines to answer.

    M4 replaces this with two directional scenarios plus an invalidation
    scenario, per owner decision D6: a successful analysis always carries a
    direction, and "no trade" is an operational outcome rather than an
    analytical one.
    """
    del structure, volatility, liquidity
    return engine_unavailable("scenarios")

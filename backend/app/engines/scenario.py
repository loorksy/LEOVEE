"""Scenario generation — real, as of M4.

Replaces the placeholder that assigned confidences of 0.55 / 0.35 / 0.4 / 0.2 by
hand and passed the winner straight through as the number the user reads as the
agent's confidence. A hand-picked constant presented as a measured probability
was the single most misleading thing this pipeline emitted.

**Two directional scenarios and one invalidation scenario** (ADR 0002). Not an
abstention scenario: a successful analysis always carries a direction, and "no
trade" is an operational outcome with a named cause rather than an analytical
verdict. The invalidation scenario answers a different question — *what would
prove this thesis wrong* — which is what makes the recommendation falsifiable
and gives the thesis monitor something concrete to watch.

Confidence is **evidence agreement**, not a guess: each scenario scores the
fraction of independent evidence that points its way. Two engines agreeing is
worth more than one engine being emphatic, and nothing here can reach certainty
because the evidence set is finite.
"""

from __future__ import annotations

from typing import Any

from app.engines.status import engine_unavailable, is_unavailable

#: Ceiling on evidence-derived confidence. Every input is a heuristic over a
#: finite window, so a scenario cannot be certain no matter how aligned the
#: evidence is; the remaining headroom is where calibration (M8) operates.
MAX_SCENARIO_CONFIDENCE = 0.85
#: Floor: a direction the evidence actively contradicts is still possible.
MIN_SCENARIO_CONFIDENCE = 0.10


def run_scenario_engine(
    structure: dict[str, Any],
    volatility: dict[str, Any],
    liquidity: dict[str, Any],
    zones: dict[str, Any] | None = None,
    mtf: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if is_unavailable(structure) or is_unavailable(liquidity):
        return engine_unavailable("scenarios")

    votes = _collect_votes(structure, liquidity, zones, mtf)
    if not votes:
        return engine_unavailable("scenarios")

    bullish_weight = sum(weight for direction, weight in votes if direction == "BULLISH")
    bearish_weight = sum(weight for direction, weight in votes if direction == "BEARISH")
    total = sum(weight for _, weight in votes)

    bullish = _confidence(bullish_weight, total)
    bearish = _confidence(bearish_weight, total)

    structure_price = float(structure.get("current_price") or 0.0)
    invalidation = _invalidation(structure, bullish >= bearish, structure_price)

    return {
        "scenarios": [
            {
                "label": "BULLISH",
                "confidence": bullish,
                "evidence": [reason for reason, direction in _reasons(votes, "BULLISH")],
            },
            {
                "label": "BEARISH",
                "confidence": bearish,
                "evidence": [reason for reason, direction in _reasons(votes, "BEARISH")],
            },
        ],
        "invalidation": invalidation,
        "evidence_count": len(votes),
        "volatility_bucket": volatility.get("bucket"),
    }


def _collect_votes(
    structure: dict[str, Any],
    liquidity: dict[str, Any],
    zones: dict[str, Any] | None,
    mtf: dict[str, Any] | None,
) -> list[tuple[str, float]]:
    """One vote per independent piece of evidence, with its weight.

    Weights are ordinal rather than tuned: structure outranks a single sweep,
    and higher-timeframe agreement outranks both, because that ordering is what
    the trading doctrine already asserts. M8 replaces them with calibrated
    values derived from realised outcomes.
    """
    votes: list[tuple[str, float]] = []

    bias = str(structure.get("bias", "NEUTRAL"))
    if bias in ("BULLISH", "BEARISH"):
        votes.append((bias, 3.0))

    # A sweep is a raid on resting orders, so it argues *against* the side that
    # was taken: buy-side liquidity taken above the highs precedes a move down.
    recent_sweep = liquidity.get("recent_sweep")
    if isinstance(recent_sweep, dict):
        side = str(recent_sweep.get("side"))
        if side == "BUY_SIDE":
            votes.append(("BEARISH", 2.0))
        elif side == "SELL_SIDE":
            votes.append(("BULLISH", 2.0))

    if zones and not is_unavailable(zones):
        demand = zones.get("demand") or []
        supply = zones.get("supply") or []
        if demand:
            votes.append(("BULLISH", 1.5 * float(demand[0].get("strength", 0.0))))
        if supply:
            votes.append(("BEARISH", 1.5 * float(supply[0].get("strength", 0.0))))

    if mtf and not is_unavailable(mtf):
        trade_bias = str(mtf.get("trade_bias", "NEUTRAL"))
        if trade_bias in ("BULLISH", "BEARISH"):
            votes.append((trade_bias, 4.0))

    return [(direction, weight) for direction, weight in votes if weight > 0]


def _reasons(votes: list[tuple[str, float]], direction: str) -> list[tuple[str, str]]:
    return [(f"weight_{weight:g}", d) for d, weight in votes if d == direction]


def _confidence(weight: float, total: float) -> float:
    if total <= 0:
        return MIN_SCENARIO_CONFIDENCE
    share = weight / total
    scaled = MIN_SCENARIO_CONFIDENCE + share * (MAX_SCENARIO_CONFIDENCE - MIN_SCENARIO_CONFIDENCE)
    return round(scaled, 4)


def _invalidation(structure: dict[str, Any], leaning_bullish: bool, price: float) -> dict[str, Any]:
    """What would prove the leading direction wrong.

    Anchored on the opposing structural level rather than a distance from
    price: a thesis is invalidated when the structure it rests on breaks, not
    when price moves an arbitrary amount.
    """
    if leaning_bullish:
        level = structure.get("nearest_support")
        return {
            "direction_invalidated": "BULLISH",
            "condition": "CLOSE_BELOW",
            "level": level,
            "description": "a close below the nearest support breaks the bullish structure",
        }
    level = structure.get("nearest_resistance")
    return {
        "direction_invalidated": "BEARISH",
        "condition": "CLOSE_ABOVE",
        "level": level,
        "description": "a close above the nearest resistance breaks the bearish structure",
    }

"""Does this plan survive its own costs?

A new name for a deliberate reason. AiChart's guard stage mixed two unrelated
jobs: it asked whether the *user* was permitted to send an order and had
confirmed it, and it asked whether the *plan* was any good. The first is out of
scope here — Leovee never places orders (D4) — but the second is not
order-placement logic at all. A stop that falls inside the live spread, or a
target that does not clear the round trip, is a **bad recommendation**, and it
stays a bad recommendation on a platform that only ever recommends.

So the order machinery is dropped entirely and the arithmetic is kept, under a
name that says what it actually does.

What it checks, in the order that matters:

1. **The stop must be a real stop.** Zero or inverted distance is not a wide
   plan, it is an unpriceable one.
2. **The stop must clear the spread.** A stop three tenths of a point away on
   gold, where the spread is three tenths of a point, is stopped out by the
   quote itself before price has moved at all.
3. **The first target must clear the round trip by a margin.** Spread and
   slippage are paid on entry *and* exit. A plan whose first target does not
   clear three times that is not slightly worse than a good one — it is
   structurally losing, and its win rate is irrelevant.
4. **Reward:risk must be positive and real**, computed from the plan's own
   levels rather than asserted by whoever wrote them.

The cost model is session-aware and honest about its provenance. When no live
spread has been observed, the fallback is *returned as* a fallback
(``source: "static_model"``) rather than as a number that implies measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.symbols import DEFAULT_SYMBOL, pip_size
from app.core.timeframes import DECISION_TIMEFRAMES
from app.models.enums import Timeframe

__all__ = [
    "MIN_COST_MULTIPLE",
    "SESSION_SPREAD_MULTIPLIER",
    "GOLD_STATIC_SPREAD_PIPS",
    "TimeframeRiskPolicy",
    "SpreadEstimate",
    "risk_policy_for",
    "session_at",
    "estimate_spread_pips",
    "round_trip_cost_pips",
    "reward_risk",
    "spread_too_high",
    "run_plan_sanity_engine",
]

#: A first target must clear this multiple of the round-trip cost.
#:
#: Governance, not a tuning knob: below it the plan is structurally losing
#: however often it wins, so lowering it does not trade accuracy for volume —
#: it just stops the check from firing.
MIN_COST_MULTIPLE = 3.0

#: Spread relative to the London baseline, by session. The *ordering* carries
#: more weight than the exact multipliers: liquidity is deepest across the
#: London/New York overlap and thinnest in Asia, and a plan that only works at
#: overlap spreads should fail at Asian ones rather than quietly pass.
SESSION_SPREAD_MULTIPLIER: dict[str, float] = {
    "asia": 1.4,
    "london": 1.0,
    "new_york": 1.1,
    "london_new_york_overlap": 0.9,
}

#: Conservative retail gold spread at the London baseline, in gold pips
#: (pip = 0.01, so 30 pips = 0.30 USD). A MODEL, never reported as a
#: measurement.
GOLD_STATIC_SPREAD_PIPS = 30.0

#: Slippage assumption, in pips, added on entry and on exit.
STATIC_SLIPPAGE_PIPS = 2.0

#: Spread is "too high" past either bound: a share of the volatility the plan
#: is sized against, or a share of the plan's own stop.
SPREAD_ATR_LIMIT = 0.15
SPREAD_STOP_LIMIT = 0.2


@dataclass(frozen=True, slots=True)
class TimeframeRiskPolicy:
    """Stop and target geometry per decision frame.

    A scalp is not a slow trade in miniature — it lives or dies on execution
    cost — so the faster frames get a tighter structural stop and a first target
    chosen to clear the round trip rather than to look ambitious. Under D11
    every frame here is a scalp; what differs is how much room the structure on
    that frame actually has.
    """

    timeframe: Timeframe
    stop_atr_multiple: float
    #: (first, second) R multiples.
    target_r: tuple[float, float]
    maximum_holding_bars: int
    break_even_at_r: float


_POLICY: dict[Timeframe, TimeframeRiskPolicy] = {
    # A one-minute scalp invalidates fast or it was never a scalp. Twelve bars
    # is twelve minutes; past that the edge has decayed and the idea is just
    # occupying attention.
    Timeframe.M1: TimeframeRiskPolicy(Timeframe.M1, 0.8, (1.2, 2.0), 12, 0.8),
    Timeframe.M5: TimeframeRiskPolicy(Timeframe.M5, 0.8, (1.2, 2.0), 12, 0.8),
    Timeframe.M15: TimeframeRiskPolicy(Timeframe.M15, 1.2, (1.5, 2.5), 18, 1.0),
}


def risk_policy_for(timeframe: Timeframe | str) -> TimeframeRiskPolicy:
    tf = Timeframe(timeframe)
    if tf not in _POLICY:
        raise ValueError(
            f"{tf.value} is not a decision timeframe; expected one of "
            f"{', '.join(t.value for t in DECISION_TIMEFRAMES)}"
        )
    return _POLICY[tf]


def session_at(moment: datetime | None = None) -> str:
    """Which liquidity session a moment falls in, by UTC hour."""
    hour = (moment or datetime.now(UTC)).astimezone(UTC).hour
    london = 7 <= hour < 16
    new_york = 12 <= hour < 21
    if london and new_york:
        return "london_new_york_overlap"
    if london:
        return "london"
    if new_york:
        return "new_york"
    return "asia"


@dataclass(frozen=True, slots=True)
class SpreadEstimate:
    pips: float
    price: float
    session: str
    #: "observed" when a live quote anchored it, "static_model" otherwise.
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pips": round(self.pips, 3),
            "price": self.price,
            "session": self.session,
            "source": self.source,
        }


def estimate_spread_pips(
    *,
    symbol: str = DEFAULT_SYMBOL,
    observed_pips: float | None = None,
    moment: datetime | None = None,
) -> SpreadEstimate:
    """The spread to price this plan against, and where the number came from.

    An observed quote is treated as a London-session reading — that is where
    most quotes are sampled, and it is the conservative anchor for the sessions
    that are cheaper than London rather than dearer.
    """
    session = session_at(moment)
    multiplier = SESSION_SPREAD_MULTIPLIER[session]
    if observed_pips is not None and observed_pips > 0:
        base, source = observed_pips, "observed"
    else:
        base, source = GOLD_STATIC_SPREAD_PIPS, "static_model"
    pips = base * multiplier
    size = pip_size(symbol) or 0.01
    return SpreadEstimate(pips=pips, price=pips * size, session=session, source=source)


def round_trip_cost_pips(spread_pips: float, slippage_pips: float = STATIC_SLIPPAGE_PIPS) -> float:
    """Both are paid twice: once getting in, once getting out."""
    return max(0.0, spread_pips) * 2 + max(0.0, slippage_pips) * 2


def reward_risk(entry: float | None, stop: float | None, target: float | None) -> float | None:
    """Reward:risk from the plan's own levels. None when it cannot be computed."""
    if entry is None or stop is None or target is None:
        return None
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if not risk > 0:
        return None
    return reward / risk


def spread_too_high(*, spread_price: float, atr: float, stop_distance: float) -> bool:
    if not spread_price > 0:
        return False
    if atr > 0 and spread_price > atr * SPREAD_ATR_LIMIT:
        return True
    return stop_distance > 0 and spread_price > stop_distance * SPREAD_STOP_LIMIT


def run_plan_sanity_engine(
    *,
    entry: float,
    stop: float,
    targets: list[float],
    atr: float,
    symbol: str = DEFAULT_SYMBOL,
    observed_spread_pips: float | None = None,
    moment: datetime | None = None,
) -> dict[str, Any]:
    """Check a plan against its own cost floor. Never touches an order."""
    size = pip_size(symbol) or 0.01
    spread = estimate_spread_pips(symbol=symbol, observed_pips=observed_spread_pips, moment=moment)
    stop_distance = abs(entry - stop)
    first_target = targets[0] if targets else None

    failures: list[str] = []
    warnings: list[str] = []

    if not stop_distance > 0:
        # Everything below divides by this, and a zero-distance stop is not a
        # wide plan — it is an unpriceable one.
        failures.append("STOP_DISTANCE_ZERO")
        return {
            "viable": False,
            "failures": failures,
            "warnings": warnings,
            "spread": spread.to_dict(),
            "stop_distance": stop_distance,
            "stop_distance_pips": 0.0,
            "round_trip_pips": round(round_trip_cost_pips(spread.pips), 2),
            "required_target_pips": None,
            "first_target_pips": None,
            "reward_risk": None,
        }

    if stop_distance <= spread.price:
        # The quote alone closes this trade before price has moved.
        failures.append("STOP_INSIDE_SPREAD")
    elif spread_too_high(spread_price=spread.price, atr=atr, stop_distance=stop_distance):
        warnings.append("SPREAD_HIGH_VS_RISK")

    round_trip = round_trip_cost_pips(spread.pips)
    required_pips = round_trip * MIN_COST_MULTIPLE
    first_target_pips = abs(first_target - entry) / size if first_target is not None else None

    if first_target is None:
        failures.append("NO_TARGET")
    elif first_target_pips is not None and first_target_pips < required_pips:
        failures.append("TARGET_BELOW_COST_FLOOR")

    rr = reward_risk(entry, stop, first_target)
    if rr is None:
        failures.append("REWARD_RISK_UNCOMPUTABLE")
    elif rr < 1.0:
        # Not fatal on its own — a high-probability setup can justify it — but
        # it must never pass unremarked.
        warnings.append("REWARD_RISK_BELOW_ONE")

    if spread.source == "static_model":
        warnings.append("SPREAD_MODELLED_NOT_OBSERVED")

    return {
        "viable": not failures,
        "failures": failures,
        "warnings": warnings,
        "spread": spread.to_dict(),
        "stop_distance": stop_distance,
        "stop_distance_pips": round(stop_distance / size, 2),
        "round_trip_pips": round(round_trip, 2),
        "required_target_pips": round(required_pips, 2),
        "first_target_pips": round(first_target_pips, 2) if first_target_pips is not None else None,
        "reward_risk": round(rr, 3) if rr is not None else None,
    }

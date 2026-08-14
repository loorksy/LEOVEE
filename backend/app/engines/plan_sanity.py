"""Does this plan survive the market it was written for?

A new name for a deliberate reason. AiChart's guard stage mixed two unrelated
jobs: whether the *user* was permitted to send an order and had confirmed it,
and whether the *plan* was any good. The first is out of scope here — Leovee
never places orders (D4) — but the second is not order-placement logic at all. A
stop that ordinary bar noise takes out, or a target price does not reach inside
the plan's own lifetime, is a **bad recommendation**, and it stays one on a
platform that only ever recommends.

**Everything here is measured from the live price. Nothing is modelled.**

An earlier version priced viability against a *modelled* retail spread — thirty
gold pips, shaped by a session table. It was a plausible number and it was
invented, and it drove a real decision: at that assumed cost the first target
had to clear 1.92 USD, which excluded one-minute gold on any ordinary tape. The
platform refused a whole timeframe because of a constant nobody had measured.

That is the same failure as a fabricated zone or a hardcoded confidence, wearing
a cost model. So the cost model is gone, and the floor comes from the candles:

**The noise floor is the median wick.** Not the bar range — that is ATR under
another name, and a stop sized as a fraction of ATR can never clear a multiple
of it, which made the first attempt at this check self-contradictory. The wick
is the part of a bar price gave back: how far it probes and returns *within* one
candle, having gone nowhere. A stop inside that is swept by a single ordinary
probe, and saying so involves no assumption about anyone's broker — the number
is in the data.

**The target floor is a multiple of ATR.** Measured volatility, not assumed
friction: a target price cannot reach in the plan's lifetime is unreachable
whatever the execution costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from app.core.symbols import DEFAULT_SYMBOL, pip_size
from app.core.timeframes import DECISION_TIMEFRAMES
from app.engines.bar import OHLCBar
from app.models.enums import Timeframe

__all__ = [
    "MIN_STOP_NOISE_MULTIPLE",
    "MIN_TARGET_ATR",
    "TimeframeRiskPolicy",
    "PriceContext",
    "measure_price_context",
    "risk_policy_for",
    "reward_risk",
    "run_plan_sanity_engine",
]

#: A stop must clear the typical wick.
#:
#: One, not a tuned constant: the claim is exactly "a stop inside the movement
#: price routinely gives back within a single candle is swept by that movement,
#: not by the thesis being wrong". Any larger multiple would be a preference
#: dressed as a measurement.
MIN_STOP_NOISE_MULTIPLE = 1.0

#: A first target must be at least this much ATR away.
#:
#: Below half an average bar's range the target is inside the next candle's
#: ordinary movement, which makes the plan a coin flip on noise rather than a
#: read of the market.
MIN_TARGET_ATR = 0.5

#: Bars the noise floor is measured over. Long enough that one violent candle
#: does not set the floor for the next hour; short enough to describe the
#: session actually being traded.
NOISE_WINDOW_BARS = 50

#: Spread is *reported* when a live quote is available, because it is real
#: information for the reader. It never gates anything: an observed spread is a
#: fact about this moment, and a plan is not made unviable by one wide print.
SPREAD_ATR_WARNING = 0.15


@dataclass(frozen=True, slots=True)
class TimeframeRiskPolicy:
    """Stop and target geometry per decision frame.

    A scalp is not a slow trade in miniature, so the faster frames get a tighter
    structural stop. Under D11 every frame here is a scalp; what differs is how
    much room the structure on that frame actually has.
    """

    timeframe: Timeframe
    stop_atr_multiple: float
    #: (first, second) R multiples.
    target_r: tuple[float, float]
    maximum_holding_bars: int
    break_even_at_r: float


_POLICY: dict[Timeframe, TimeframeRiskPolicy] = {
    # A one-minute scalp invalidates fast or it was never a scalp. Twelve bars
    # is twelve minutes; past that the edge has decayed.
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


@dataclass(frozen=True, slots=True)
class PriceContext:
    """What the candles say about how this market moves right now."""

    #: Median wick per bar — the part of the range price gave back. Movement
    #: that went nowhere, measured rather than assumed.
    noise: float
    atr: float
    last_close: float
    bars: int
    #: Present only when a live quote was supplied. Reported, never a gate.
    observed_spread: float | None = None

    @property
    def usable(self) -> bool:
        return self.bars > 0 and self.noise > 0 and self.atr > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "noise": round(self.noise, 5),
            "atr": round(self.atr, 5),
            "last_close": self.last_close,
            "bars": self.bars,
            "observed_spread": self.observed_spread,
        }


def measure_price_context(
    bars: list[OHLCBar],
    *,
    atr: float,
    observed_spread: float | None = None,
    window: int = NOISE_WINDOW_BARS,
) -> PriceContext:
    """Read the floor off the tape.

    The wick, not the range: the range *is* ATR, so a floor built on it makes a
    stop sized as a fraction of ATR unable to clear a multiple of it by
    construction — the check would reject every scalp for arithmetic reasons.
    The wick is what price gave back, which is the thing a stop has to survive.

    The median, not the mean: one payrolls candle drags a mean far enough that
    every stop after it looks generous, which is exactly backwards.
    """
    recent = bars[-window:]
    wicks = [
        (bar.high - bar.low) - abs(bar.close - bar.open) for bar in recent if bar.high > bar.low
    ]
    return PriceContext(
        noise=median(wicks) if wicks else 0.0,
        atr=atr,
        last_close=recent[-1].close if recent else 0.0,
        bars=len(recent),
        observed_spread=observed_spread,
    )


def reward_risk(entry: float | None, stop: float | None, target: float | None) -> float | None:
    """Reward:risk from the plan's own levels. None when it cannot be computed."""
    if entry is None or stop is None or target is None:
        return None
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if not risk > 0:
        return None
    return reward / risk


def run_plan_sanity_engine(
    *,
    entry: float,
    stop: float,
    targets: list[float],
    context: PriceContext,
    symbol: str = DEFAULT_SYMBOL,
) -> dict[str, Any]:
    """Check a plan against the market it was written for. Never touches an order."""
    size = pip_size(symbol) or 0.01
    stop_distance = abs(entry - stop)
    first_target = targets[0] if targets else None

    failures: list[str] = []
    warnings: list[str] = []

    if not stop_distance > 0:
        # Everything below divides by this, and a zero-distance stop is not a
        # wide plan — it is an unpriceable one.
        return {
            "viable": False,
            "failures": ["STOP_DISTANCE_ZERO"],
            "warnings": warnings,
            "context": context.to_dict(),
            "stop_distance": stop_distance,
            "stop_distance_pips": 0.0,
            "stop_noise_multiple": None,
            "first_target_atr": None,
            "required_stop_distance": None,
            "reward_risk": None,
        }

    if not context.usable:
        # No measured floor means the check cannot run. Declining to judge is
        # honest; passing everything would turn a missing measurement into a
        # blanket approval.
        failures.append("NO_PRICE_CONTEXT")

    stop_noise_multiple: float | None = None
    required_stop = None
    if context.noise > 0:
        stop_noise_multiple = stop_distance / context.noise
        required_stop = context.noise * MIN_STOP_NOISE_MULTIPLE
        if stop_distance < required_stop:
            # Taken out by ordinary movement rather than by the thesis being
            # wrong. Measured from this market's own candles, not assumed.
            failures.append("STOP_INSIDE_NOISE")

    first_target_atr: float | None = None
    if first_target is None:
        failures.append("NO_TARGET")
    elif context.atr > 0:
        first_target_atr = abs(first_target - entry) / context.atr
        if first_target_atr < MIN_TARGET_ATR:
            failures.append("TARGET_INSIDE_NOISE")

    rr = reward_risk(entry, stop, first_target)
    if rr is None:
        failures.append("REWARD_RISK_UNCOMPUTABLE")
    elif rr < 1.0:
        # Not fatal on its own — a high-probability setup can justify it — but
        # it must never pass unremarked.
        warnings.append("REWARD_RISK_BELOW_ONE")

    if (
        context.observed_spread is not None
        and context.atr > 0
        and context.observed_spread > context.atr * SPREAD_ATR_WARNING
    ):
        # A warning, never a gate. One wide print is a fact about this instant,
        # and a plan is not unviable because of it.
        warnings.append("SPREAD_WIDE_RIGHT_NOW")

    return {
        "viable": not failures,
        "failures": failures,
        "warnings": warnings,
        "context": context.to_dict(),
        "stop_distance": stop_distance,
        "stop_distance_pips": round(stop_distance / size, 2),
        "stop_noise_multiple": (
            round(stop_noise_multiple, 2) if stop_noise_multiple is not None else None
        ),
        "required_stop_distance": round(required_stop, 5) if required_stop is not None else None,
        "first_target_atr": round(first_target_atr, 2) if first_target_atr is not None else None,
        "reward_risk": round(rr, 3) if rr is not None else None,
    }

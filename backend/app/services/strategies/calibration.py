"""How confident the record actually justifies being.

A win rate is a point estimate, and a point estimate from eleven trades is a
number with no business being shown next to one from four hundred. What matters
is the *interval*, and how the interval behaves when the sample is thin.

**Two regimes, and the boundary is a decision rather than a gradient.**

Below ``MIN_TRADES_FOR_CALIBRATION`` the interval is a Wilson score interval —
the honest binomial answer, which stays inside [0, 1] and stays wide when it
should. A plain IID bootstrap is *degenerate* here: resampling one observation
always yields 0% or 100%, so the bootstrap would report a confident interval of
zero width on a sample of one. That is not a conservative failure; it is the
most dangerous possible one, because it reads as certainty.

At or above the floor the interval is a nonparametric bootstrap over the actual
outcomes, seeded so a re-run reproduces it exactly. A stated confidence that
changes between two identical questions is not a measurement.

**This is not backtesting (D7).** The outcomes resampled here are real closed
recommendations. A confidence interval over observed results is a description of
what happened; a backtest is a simulation of what might have. The distinction is
the entire reason this package is allowed to exist.

Ported from AiChart's ``strategies/calibration.ts`` against golden fixtures
generated from that implementation — see
``app/tests/fixtures/golden/strategy_calibration.json``. The JS-to-Python traps
that matter here are unsigned 32-bit shifts and ``Math.floor`` on negatives;
both are handled explicitly rather than trusted to look similar.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "MIN_TRADES_FOR_CALIBRATION",
    "DEFAULT_ITERATIONS",
    "DEFAULT_SEED",
    "Z_90",
    "Z_95",
    "WinRateCalibration",
    "wilson_score_interval",
    "calibrate_win_rate",
]

#: Below this many closed outcomes the sample cannot support a bootstrap.
#:
#: Not a tuning knob: at n=1 an IID resample returns 0% or 100% every time, so
#: the interval collapses to zero width exactly when the evidence is weakest.
MIN_TRADES_FOR_CALIBRATION = 30

DEFAULT_ITERATIONS = 2000

#: Fixed, and part of the contract. An unseeded bootstrap gives two different
#: confidences for the same record, which makes the number unfalsifiable.
DEFAULT_SEED = 0xA1C4A7

#: ~90% two-sided, the default band.
Z_90 = 1.6448536269514722
#: ~95%, used when the caller asks for a confidence level of 0.95 or higher.
Z_95 = 1.959963984540054

_UINT32 = 0xFFFFFFFF


@dataclass(frozen=True, slots=True)
class WinRateCalibration:
    method: Literal["wilson", "bootstrap_iid"]
    samples: int
    iterations: int
    win_rate: float
    confidence_low: float
    confidence_high: float
    #: False below the floor. The caller must surface this rather than quietly
    #: publishing a midpoint the sample cannot support.
    statistically_sufficient: bool
    seed: int

    @property
    def width(self) -> float:
        return self.confidence_high - self.confidence_low

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "samples": self.samples,
            "iterations": self.iterations,
            "win_rate": self.win_rate,
            "confidence_low": self.confidence_low,
            "confidence_high": self.confidence_high,
            "statistically_sufficient": self.statistically_sufficient,
            "seed": self.seed,
        }


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _xorshift32(seed: int) -> Iterator[float]:
    """The reference PRNG, with JavaScript's unsigned 32-bit semantics made explicit.

    In JS every step is implicitly truncated: ``<<`` and ``^`` operate on 32-bit
    signed integers and ``>>> 0`` reinterprets the result as unsigned. Python's
    integers are unbounded, so without the masks the state grows without limit
    and the sequence diverges from the reference after the first iteration —
    silently, into numbers that still look like plausible random floats.
    """
    state = seed & _UINT32
    if state == 0:
        state = 0x9E3779B9
    while True:
        state ^= (state << 13) & _UINT32
        state ^= state >> 17
        state ^= (state << 5) & _UINT32
        state &= _UINT32
        yield state / 0x100000000


def wilson_score_interval(wins: int, samples: int, z: float = Z_90) -> tuple[float, float]:
    """The honest binomial interval for a proportion.

    Asymmetric near the edges, which is the point: nine wins from ten is not
    evidence of a 90% strategy, and a symmetric interval says it is.
    """
    if samples <= 0:
        # No observations is not a 50% estimate with a wide band — it is the
        # whole range, and the caller has to notice.
        return 0.0, 1.0
    p = wins / samples
    z2 = z * z
    denom = 1 + z2 / samples
    center = p + z2 / (2 * samples)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * samples)) / samples)
    return _clamp01((center - margin) / denom), _clamp01((center + margin) / denom)


def calibrate_win_rate(
    *,
    wins: float,
    samples: float,
    iterations: int = DEFAULT_ITERATIONS,
    confidence_level: float = 0.9,
    seed: int = DEFAULT_SEED,
    min_trades: int = MIN_TRADES_FOR_CALIBRATION,
) -> WinRateCalibration:
    """A win rate with the interval its sample size actually supports."""
    # math.floor, matching JS: it rounds toward negative infinity, so a negative
    # count floors *away* from zero before the max() clamps it. int() would
    # truncate toward zero and disagree on exactly those inputs.
    wins_i = max(0, math.floor(wins))
    samples_i = max(0, math.floor(samples))
    iterations = max(200, math.floor(iterations))
    confidence_level = min(0.99, max(0.5, confidence_level))
    seed = math.floor(seed)
    floor_n = max(2, math.floor(min_trades))
    win_rate = wins_i / samples_i if samples_i > 0 else 0.0
    alpha = 1 - confidence_level
    z = Z_95 if confidence_level >= 0.95 else Z_90

    if samples_i <= 0:
        return WinRateCalibration(
            method="wilson",
            samples=0,
            iterations=0,
            win_rate=0.0,
            confidence_low=0.0,
            confidence_high=1.0,
            statistically_sufficient=False,
            seed=seed,
        )

    if samples_i < floor_n:
        low, high = wilson_score_interval(wins_i, samples_i, z)
        return WinRateCalibration(
            method="wilson",
            samples=samples_i,
            iterations=0,
            win_rate=win_rate,
            confidence_low=low,
            confidence_high=high,
            statistically_sufficient=False,
            seed=seed,
        )

    # The outcome list is wins-first rather than shuffled. It does not matter
    # statistically — an IID resample draws with replacement from the whole list
    # — but it is what the reference does, and reproducing the reference's
    # exact draws is what makes the golden fixtures meaningful.
    outcomes = [index < wins_i for index in range(samples_i)]
    rng = _xorshift32(seed)
    rates: list[float] = []
    for _ in range(iterations):
        resample_wins = 0
        for _ in range(samples_i):
            if outcomes[math.floor(next(rng) * samples_i)]:
                resample_wins += 1
        rates.append(resample_wins / samples_i)
    rates.sort()
    low_index = max(0, min(len(rates) - 1, math.floor((alpha / 2) * len(rates))))
    high_index = max(0, min(len(rates) - 1, math.floor((1 - alpha / 2) * len(rates))))

    return WinRateCalibration(
        method="bootstrap_iid",
        samples=samples_i,
        iterations=iterations,
        win_rate=win_rate,
        confidence_low=_clamp01(rates[low_index]),
        confidence_high=_clamp01(rates[high_index]),
        statistically_sufficient=True,
        seed=seed,
    )

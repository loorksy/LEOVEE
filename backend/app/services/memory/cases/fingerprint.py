"""What one market moment looked like, in terms another moment can be compared to.

"When has it looked like this before, and what came next" had no answer. The
memory held lessons and conversation summaries — what the *operator* did — and
nothing about what the *market* did, so a setup could never be compared against
its own history.

A fingerprint describes a moment structurally: regime, trend, where price sits
in its range, how deep the last pullback ran, how strong the last impulse was,
volatility, session, and how many bars have been extending the structure.
Similarity is similarity of those features — deliberately not of the picture,
which matches on cosmetics and misses the setup.

**The constraint that makes it honest: a fingerprint is computed only from
candles at or before its own timestamp.** One later bar leaking into one feature
turns the whole memory into a machine for predicting the past, and it would do
so while looking exactly as convincing.

**Similarity is weighted L1, not cosine.** Cosine over these eight slots would
call two moments alike for pointing the same way regardless of magnitude, and
the magnitudes are the setup. Cosine appears in this system only as a *recall*
device — pgvector narrowing candidates — never as the ranking metric.

Ported from AiChart's `marketMemory/caseFingerprint.ts` against golden fixtures
generated from it (`app/tests/fixtures/golden/case_fingerprint.json`), with one
documented, tested difference — see `RECENT_ATR_PERIOD`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.numeric import js_to_fixed
from app.engines.bar import OHLCBar

__all__ = [
    "MIN_CANDLES",
    "RANGE_WINDOW",
    "ATR_PERIOD",
    "WEIGHTS",
    "CaseFingerprint",
    "fingerprint_at",
    "fingerprint_vector",
    "fingerprint_similarity",
    "session_of",
]

Regime = Literal["trend", "range", "volatile"]
Trend = Literal["up", "down", "flat"]
RangeZone = Literal["near_low", "discount", "mid", "premium", "near_high"]
Session = Literal["asia", "london", "newyork"]

#: Below this the range and trend features are computed over a window that does
#: not exist. Refusing is the answer, not a smaller window.
MIN_CANDLES = 30

#: Everything structural is measured over this slice. When fewer bars exist the
#: slice is the whole series and the trend baseline moves — faithfully ported,
#: because the fixtures at 30 and 45 bars pin exactly that behaviour.
RANGE_WINDOW = 60

ATR_PERIOD = 14

#: The volatility comparison's short leg.
#:
#: **The one intentional difference from the reference**, and it took two
#: attempts to get right.
#:
#: In the reference, `recentAtr = atrOf(candles.slice(-15), 14)` while
#: `atr = atrOf(candles)` — and `atrOf` itself slices `[-(period+1):]`, i.e. the
#: last 15. Slicing the last 15 and then taking the last 15 of that is the same
#: fifteen bars, so `recentAtr` was always *identical* to `atr`, the ratio was
#: always exactly 1.0, and **`regime == "volatile"` could never occur**. Verified
#: rather than argued: a fixture whose final twelve bars carry a sixfold
#: volatility burst still comes back `trend`.
#:
#: The obvious repair — a genuinely shorter period, ATR(7) against ATR(14) — does
#: not work either, and measuring it is the only way to find that out. The two
#: windows overlap almost completely, so the ratio is structurally pinned near 1:
#: on that same burst fixture it reaches 1.10, nowhere near the 1.5 threshold.
#: One dead branch replaced by a slightly less dead one is not a fix, it is the
#: same silence with better-looking code.
#:
#: What works is a baseline that **excludes** the window being judged: ATR over
#: the last seven bars against ATR over the structural window *before* them. On
#: the burst fixture that reads 1.97 and classifies `volatile`; every ordinary
#: tape in the fixture set stays between 0.83 and 1.24. That is a classifier
#: that can actually say the third thing it claims to be able to say.
RECENT_ATR_PERIOD = 7

TREND_ATR_MULTIPLE = 1.5
RANGE_ATR_TREND_THRESHOLD = 6.0
VOLATILITY_RATIO_THRESHOLD = 1.5
IMPULSE_LOOKBACK = 10

#: Per-slot weights, in contract order. Trend is heaviest and session lightest:
#: two moments differing only in session are far more alike than two differing
#: in direction, and equal weights would bury that.
WEIGHTS = (1.0, 1.4, 1.0, 0.8, 0.8, 0.7, 0.4, 0.6)
_WEIGHT_TOTAL = sum(WEIGHTS)

_REGIME_SLOT: dict[str, float] = {"trend": 1.0, "range": 0.0, "volatile": 0.5}
_TREND_SLOT: dict[str, float] = {"up": 1.0, "down": -1.0, "flat": 0.0}
_ZONE_SLOT: dict[str, float] = {
    "near_low": 0.0,
    "discount": 0.25,
    "mid": 0.5,
    "premium": 0.75,
    "near_high": 1.0,
}
_SESSION_SLOT: dict[str, float] = {"asia": 0.0, "london": 0.5, "newyork": 1.0}


@dataclass(frozen=True, slots=True)
class CaseFingerprint:
    regime: Regime
    trend: Trend
    range_zone: RangeZone
    #: Retracement of the last impulse, 0–1.
    pullback_depth: float
    #: Size of the last impulse in ATR. Unbounded; the vector clamps it.
    impulse_atr: float
    #: ATR as a fraction of price.
    volatility: float
    session: Session
    #: Consecutive bars extending the structure into this moment.
    structure_run: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "trend": self.trend,
            "range_zone": self.range_zone,
            "pullback_depth": self.pullback_depth,
            "impulse_atr": self.impulse_atr,
            "volatility": self.volatility,
            "session": self.session,
            "structure_run": self.structure_run,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CaseFingerprint:
        return cls(
            regime=payload["regime"],
            trend=payload["trend"],
            range_zone=payload.get("range_zone") or payload["rangeZone"],
            pullback_depth=float(payload.get("pullback_depth", payload.get("pullbackDepth", 0.0))),
            impulse_atr=float(payload.get("impulse_atr", payload.get("impulseAtr", 0.0))),
            volatility=float(payload["volatility"]),
            session=payload["session"],
            structure_run=int(payload.get("structure_run", payload.get("structureRun", 0))),
        )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _atr_of(bars: list[OHLCBar], period: int = ATR_PERIOD) -> float:
    """True range averaged over the tail.

    The divisor is the *window's* length minus one, not `period`. On a short
    series that means a mean over fewer bars without saying so — ported as-is,
    because the 30-bar fixture depends on it and changing it would move every
    feature that scales by ATR.
    """
    window = bars[-(period + 1) :]
    if len(window) < 2:
        return 0.0
    total = 0.0
    for index in range(1, len(window)):
        previous = window[index - 1]
        current = window[index]
        total += max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
    return total / (len(window) - 1)


def session_of(moment: datetime) -> Session:
    """Which session an instant belongs to, by UTC hour.

    UTC explicitly. Reading the server's local hour would make the same candle
    fingerprint differently depending on where the process runs, and the
    difference would only show up as slightly worse recall.
    """
    hour = moment.astimezone(UTC).hour
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 21:
        return "newyork"
    return "asia"


def fingerprint_at(bars: list[OHLCBar]) -> CaseFingerprint | None:
    """Fingerprint the moment ending at the last bar.

    Callers pass a window ending where the case sits. Passing later bars is the
    lookahead this whole design exists to prevent, and nothing downstream could
    detect it.
    """
    if len(bars) < MIN_CANDLES:
        return None
    last = bars[-1]
    atr = _atr_of(bars)
    if not atr > 0 or not last.close > 0:
        return None

    window = bars[-RANGE_WINDOW:]
    highs = [bar.high for bar in window]
    lows = [bar.low for bar in window]
    range_high = max(highs)
    range_low = min(lows)
    # Epsilon rather than a guard clause: a perfectly flat window is a real
    # market state, and it should fingerprint as one rather than be refused.
    span = max(range_high - range_low, sys.float_info.epsilon)
    position = (last.close - range_low) / span

    if position >= 0.95:
        range_zone: RangeZone = "near_high"
    elif position >= 0.62:
        range_zone = "premium"
    elif position <= 0.05:
        range_zone = "near_low"
    elif position <= 0.38:
        range_zone = "discount"
    else:
        range_zone = "mid"

    net_move = last.close - window[0].close
    if net_move > atr * TREND_ATR_MULTIPLE:
        trend: Trend = "up"
    elif net_move < -atr * TREND_ATR_MULTIPLE:
        trend = "down"
    else:
        trend = "flat"

    range_atr = span / atr
    recent_atr = _atr_of(bars, RECENT_ATR_PERIOD)
    # The baseline excludes the bars being judged. Comparing a window against a
    # longer window that contains it measures mostly itself.
    baseline_bars = window[:-RECENT_ATR_PERIOD]
    baseline_atr = _atr_of(baseline_bars) if len(baseline_bars) >= 2 else 0.0
    volatility_ratio = recent_atr / baseline_atr if baseline_atr > 0 else 1.0
    if volatility_ratio > VOLATILITY_RATIO_THRESHOLD:
        regime: Regime = "volatile"
    elif range_atr > RANGE_ATR_TREND_THRESHOLD and trend != "flat":
        regime = "trend"
    else:
        regime = "range"

    # First occurrence, and `flat` takes the high branch. Both are load-bearing:
    # a repeated extreme picks the earliest bar, which puts the impulse start
    # ten bars before *that* one.
    extreme_index = lows.index(range_low) if trend == "down" else highs.index(range_high)
    impulse_start = window[max(0, extreme_index - IMPULSE_LOOKBACK)].close
    # A close against a wick, deliberately: the impulse ends at the extreme price
    # actually printed, not at where the bar happened to settle.
    impulse_end = range_low if trend == "down" else range_high
    impulse = abs(impulse_end - impulse_start)
    retraced = abs(last.close - impulse_end)
    pullback_depth = min(1.0, retraced / impulse) if impulse > 0 else 0.0

    structure_run = 0
    for index in range(len(window) - 1, 0, -1):
        current = window[index]
        previous = window[index - 1]
        extending = current.low < previous.low if trend == "down" else current.high > previous.high
        if not extending:
            break
        structure_run += 1

    return CaseFingerprint(
        regime=regime,
        trend=trend,
        range_zone=range_zone,
        # Rounded at construction, so every similarity is computed from the
        # rounded value and not from a fuller one that was never stored.
        pullback_depth=js_to_fixed(pullback_depth, 3),
        impulse_atr=js_to_fixed(impulse / atr, 2),
        volatility=js_to_fixed(atr / last.close, 5),
        session=session_of(last.ts),
        structure_run=structure_run,
    )


def fingerprint_vector(fingerprint: CaseFingerprint) -> list[float]:
    """The eight slots, in contract order. The order is persisted, so it is frozen.

    Slot 1 is the only one that can be negative: up is +1 and down is −1, which
    makes a trend disagreement the largest single distance available and is why
    it carries the heaviest weight.
    """
    return [
        _REGIME_SLOT[fingerprint.regime],
        _TREND_SLOT[fingerprint.trend],
        _ZONE_SLOT[fingerprint.range_zone],
        _clamp01(fingerprint.pullback_depth),
        _clamp01(fingerprint.impulse_atr / 5),
        _clamp01(fingerprint.volatility * 200),
        _SESSION_SLOT[fingerprint.session],
        _clamp01(fingerprint.structure_run / 6),
    ]


def fingerprint_similarity(a: CaseFingerprint, b: CaseFingerprint) -> float:
    """0–1, weighted L1. Identical fingerprints give exactly 1.0."""
    va = fingerprint_vector(a)
    vb = fingerprint_vector(b)
    weighted = sum(weight * abs(x - y) for weight, x, y in zip(WEIGHTS, va, vb, strict=True))
    return max(0.0, 1 - weighted / _WEIGHT_TOTAL)

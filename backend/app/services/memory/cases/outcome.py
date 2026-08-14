"""What happened *after* a moment, and what a set of those adds up to.

A fingerprint says what the market looked like. This says how it resolved.
Together they answer the question the platform could never ask: *when it looked
like this before, did the move pay?*

**The separation is the honesty.** Features come from candles at or before the
moment; outcomes come from candles strictly after it. Mixing them produces a
memory that predicts the past perfectly and the future not at all — so they live
in different functions, taking different inputs, and nothing can wire them the
wrong way by accident.

**The stop wins a tie.** When one bar touches both levels, OHLC alone cannot say
which came first. Assuming the good one is how a study lies to itself, and it
lies in the flattering direction every time.

**No execution cost (ADR 0010).** The reference charged a round-trip cost to both
legs. Leovee models no spread and fills nothing, so the cost is gone — which
makes `net_r` exactly `-1.0` on a stop and `2.0` on a target. That is not a loss
of information: the information was always in *which* resolution happened and
how far price ran either way, and a constant that pretended to be a measurement
was the part worth removing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.numeric import js_to_fixed
from app.engines.bar import OHLCBar

__all__ = [
    "STOP_ATR",
    "TARGET_ATR",
    "MIN_STATS_SAMPLE",
    "DEFAULT_HORIZON",
    "CaseResolution",
    "ForwardOutcome",
    "OutcomeStats",
    "resolve_forward_outcome",
    "summarize_outcomes",
]

#: The plan every historical case is measured against: stop at one ATR, first
#: target at two. Fixed rather than per-case, because the point is to compare
#: *moments*, and a different plan per moment would compare the plans instead.
STOP_ATR = 1.0
TARGET_ATR = 2.0

#: Bars to walk before giving up. A case that has not resolved in forty bars did
#: not resolve — recording it as such is a real third answer, not a gap.
DEFAULT_HORIZON = 40

#: Below this many cases the rates are withheld. "Three of four worked" invites a
#: conclusion the data cannot support, and this memory exists to inform a
#: decision rather than to decorate it.
MIN_STATS_SAMPLE = 8


class CaseResolution(StrEnum):
    TARGET_FIRST = "target_first"
    STOP_FIRST = "stop_first"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ForwardOutcome:
    resolution: CaseResolution
    #: Bars until resolution, or the horizon when it never resolved.
    bars: int
    #: Best excursion in the tested direction, in ATR.
    max_favourable_atr: float
    #: Worst excursion against it, in ATR.
    max_adverse_atr: float
    net_r: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution": self.resolution.value,
            "bars": self.bars,
            "max_favourable_atr": self.max_favourable_atr,
            "max_adverse_atr": self.max_adverse_atr,
            "net_r": self.net_r,
        }


@dataclass(frozen=True, slots=True)
class OutcomeStats:
    sample_size: int
    target_first: int
    stop_first: int
    unresolved: int
    #: None below the sample floor, and None when nothing resolved either way.
    hit_rate: float | None
    average_net_r: float | None
    average_bars: float | None

    @property
    def sufficient(self) -> bool:
        return self.sample_size >= MIN_STATS_SAMPLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "target_first": self.target_first,
            "stop_first": self.stop_first,
            "unresolved": self.unresolved,
            "hit_rate": self.hit_rate,
            "average_net_r": self.average_net_r,
            "average_bars": self.average_bars,
        }


def _round(value: float) -> float:
    return js_to_fixed(value, 3)


def resolve_forward_outcome(
    *,
    direction: str,
    entry: float,
    atr: float,
    future: Sequence[OHLCBar],
    horizon: int = DEFAULT_HORIZON,
) -> ForwardOutcome:
    """Walk one case forward to its resolution.

    ``future`` must contain **only** bars after the case's own timestamp. That
    is the single rule keeping this memory honest, and nothing downstream can
    detect a violation of it — so it is stated here rather than assumed at the
    call site.
    """
    walked = min(horizon, len(future))
    long = direction == "buy"
    stop = entry - atr * STOP_ATR if long else entry + atr * STOP_ATR
    target = entry + atr * TARGET_ATR if long else entry - atr * TARGET_ATR

    max_favourable = 0.0
    max_adverse = 0.0

    for index in range(walked):
        bar = future[index]
        favourable = bar.high - entry if long else entry - bar.low
        adverse = entry - bar.low if long else bar.high - entry
        max_favourable = max(max_favourable, favourable)
        max_adverse = max(max_adverse, adverse)

        hit_stop = bar.low <= stop if long else bar.high >= stop
        hit_target = bar.high >= target if long else bar.low <= target

        # Checked before the target, inside the same bar. From OHLC alone the
        # order within a bar is unknowable; resolving the ambiguity toward the
        # loss is the only choice that cannot flatter the record.
        if hit_stop:
            return ForwardOutcome(
                resolution=CaseResolution.STOP_FIRST,
                bars=index + 1,
                max_favourable_atr=_round(max_favourable / atr),
                max_adverse_atr=_round(max_adverse / atr),
                net_r=-1.0,
            )
        if hit_target:
            return ForwardOutcome(
                resolution=CaseResolution.TARGET_FIRST,
                bars=index + 1,
                max_favourable_atr=_round(max_favourable / atr),
                max_adverse_atr=_round(max_adverse / atr),
                net_r=_round(TARGET_ATR / STOP_ATR),
            )

    return ForwardOutcome(
        resolution=CaseResolution.UNRESOLVED,
        bars=walked,
        max_favourable_atr=_round(max_favourable / atr),
        max_adverse_atr=_round(max_adverse / atr),
        net_r=0.0,
    )


def summarize_outcomes(outcomes: Sequence[ForwardOutcome]) -> OutcomeStats:
    """Aggregate a set of resolutions, under the minimum-sample rule.

    Three different denominators, deliberately, because they answer three
    different questions:

    - **hit rate** divides by the *resolved* cases. An unresolved case is not a
      loss — it is a case the plan never got an answer from — and putting it in
      the denominator would report an edge as weaker the more often it simply
      ran out of time.
    - **average net R** and **average bars** divide by the *whole* sample.
      Unresolved cases contribute 0R and their full horizon, which is exactly
      what they cost: nothing, slowly.
    """
    sample_size = len(outcomes)
    target_first = sum(1 for o in outcomes if o.resolution is CaseResolution.TARGET_FIRST)
    stop_first = sum(1 for o in outcomes if o.resolution is CaseResolution.STOP_FIRST)
    unresolved = sum(1 for o in outcomes if o.resolution is CaseResolution.UNRESOLVED)
    resolved = target_first + stop_first

    if sample_size < MIN_STATS_SAMPLE:
        # Counts, no rates. The reader gets to see there were three cases; what
        # they must not be handed is a percentage computed from three.
        return OutcomeStats(
            sample_size=sample_size,
            target_first=target_first,
            stop_first=stop_first,
            unresolved=unresolved,
            hit_rate=None,
            average_net_r=None,
            average_bars=None,
        )

    return OutcomeStats(
        sample_size=sample_size,
        target_first=target_first,
        stop_first=stop_first,
        unresolved=unresolved,
        hit_rate=target_first / resolved if resolved > 0 else None,
        average_net_r=_round(sum(o.net_r for o in outcomes) / max(1, sample_size)),
        average_bars=_round(sum(o.bars for o in outcomes) / max(1, sample_size)),
    )

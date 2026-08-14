"""Swing pivots — the input every pattern detector consumes.

Ported from AiChart's ``src/lib/chart/geometry/pivots.ts``. Two stages:

1. ``confirmed_pivots`` — fractal swings confirmed by ``lookback`` bars either
   side;
2. ``zigzag_pivots`` — an alternating high/low sequence in which every leg moves
   at least ``min_move_atr × ATR``, so the pattern templates see structure
   rather than noise.

**The plateau rule is asymmetric and that is deliberate.** For a low, an equal
low on the *right* is tolerated while an equal low on the *left* disqualifies.
The effect is that the first bar of a flat run is the pivot and later duplicates
defer to it. Symmetric rules either emit a pivot per bar of the plateau — which
a double-bottom template then reads as several bottoms — or emit none at all,
losing the flat double low entirely.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.engines.bar import OHLCBar

__all__ = [
    "PivotKind",
    "Pivot",
    "DEFAULT_PIVOT_LOOKBACK",
    "DEFAULT_ZIGZAG_MIN_MOVE_ATR",
    "confirmed_pivots",
    "all_confirmed_pivots",
    "zigzag_pivots",
    "geometry_atr",
]

PivotKind = Literal["high", "low"]

DEFAULT_PIVOT_LOOKBACK = 3
DEFAULT_ZIGZAG_MIN_MOVE_ATR = 0.5


@dataclass(frozen=True, slots=True)
class Pivot:
    index: int
    ts: datetime
    price: float
    kind: PivotKind


def confirmed_pivots(
    bars: list[OHLCBar],
    side: PivotKind,
    lookback: int = DEFAULT_PIVOT_LOOKBACK,
) -> list[Pivot]:
    """Fractal swings on one side, confirmed by `lookback` bars each way."""
    out: list[Pivot] = []
    # Clamped: below 1 confirms nothing, above 5 needs so much confirmation that
    # a scalp series yields no pivots at all.
    lb = max(1, min(5, int(lookback)))
    for i in range(lb, len(bars) - lb):
        bar = bars[i]
        price = bar.low if side == "low" else bar.high
        ok = True
        for j in range(1, lb + 1):
            left = bars[i - j].low if side == "low" else bars[i - j].high
            right = bars[i + j].low if side == "low" else bars[i + j].high
            if side == "low":
                # Equal-or-lower on the left disqualifies (the first bar of a
                # run wins); strictly lower on the right disqualifies, equal
                # passes so a plateau still yields its leading pivot.
                if left <= price or right < price:
                    ok = False
                    break
            elif left >= price or right > price:
                ok = False
                break
        if ok:
            out.append(Pivot(index=i, ts=bar.ts, price=price, kind=side))
    return out


def all_confirmed_pivots(
    bars: list[OHLCBar], lookback: int = DEFAULT_PIVOT_LOOKBACK
) -> list[Pivot]:
    """Both sides merged in index order; on a tie a high precedes a low."""
    merged = confirmed_pivots(bars, "high", lookback) + confirmed_pivots(bars, "low", lookback)
    # The tie-break matters: a bar that is both a swing high and a swing low
    # (an inside-bar plateau) must order deterministically or the zigzag below
    # alternates differently between runs.
    merged.sort(key=lambda p: (p.index, 0 if p.kind == "high" else 1))
    return merged


def zigzag_pivots(
    bars: list[OHLCBar],
    atr_value: float,
    *,
    lookback: int | None = None,
    min_move_atr: float | None = None,
) -> list[Pivot]:
    """Alternating high/low sequence over the confirmed pivots.

    Consecutive same-side pivots collapse to the more extreme one, and a
    direction change is accepted only when the leg moves far enough to be worth
    calling a leg. Strict alternation is what the head-and-shoulders,
    double-top and flag templates are written against.
    """
    move = max(0.1, DEFAULT_ZIGZAG_MIN_MOVE_ATR if min_move_atr is None else min_move_atr)
    # sys.float_info.epsilon stands in for JavaScript's Number.EPSILON: with a
    # zero ATR the threshold must stay positive or every leg qualifies.
    min_move = move * max(atr_value, sys.float_info.epsilon)
    raw = all_confirmed_pivots(bars, DEFAULT_PIVOT_LOOKBACK if lookback is None else lookback)
    if not raw:
        return []

    out: list[Pivot] = []
    for pivot in raw:
        if not out:
            out.append(pivot)
            continue
        last = out[-1]
        if pivot.kind == last.kind:
            more_extreme = (
                pivot.price > last.price if pivot.kind == "high" else pivot.price < last.price
            )
            if more_extreme:
                out[-1] = pivot
            continue
        if abs(pivot.price - last.price) < min_move:
            continue
        out.append(pivot)
    return out


def geometry_atr(bars: list[OHLCBar], period: int = 14) -> float:
    """ATR over a widened window, returning 0 rather than None.

    The geometry engine multiplies this to size its thresholds, so it needs a
    number in every case; zero degrades the zigzag to "every leg counts", which
    is the conservative direction. The window is deliberately wider than the
    period — a scalp series is noisy enough that a 14-bar view of volatility
    swings with each spike.
    """
    if len(bars) < 2:
        return 0.0
    window = bars[-max(period * 4, 56) :]
    trs: list[float] = []
    for i in range(1, len(window)):
        current = window[i]
        prev = window[i - 1]
        trs.append(
            max(
                current.high - current.low,
                abs(current.high - prev.close),
                abs(current.low - prev.close),
            )
        )
    if not trs:
        return 0.0
    tail = trs[-period:]
    return sum(tail) / len(tail)

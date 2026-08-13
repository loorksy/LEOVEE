"""Trendlines as envelopes, not merely two connectable pivots.

Ported from AiChart's ``trendlines.ts``. Any two pivots can be joined by a line;
what makes a line a *trendline* is that price respected it, and the rules below
encode exactly that. Each one exists because a looser version produced lines a
trader would not draw:

**Envelope rule (close-based).** From the first anchor to the last candle, no
candle may *close* beyond the line by more than 0.25×ATR. Wicks may pierce — a
spike stop-run does not invalidate a respected line — but a body settling
through it does. One rule covers both interior containment and the classic
post-anchor break; scanning only after the second anchor let a "support" slice
straight through a dip between its own anchors.

**Touches are pivots, not bars.** A touch is a same-side pivot within 0.15×ATR
of the line, counted from the first anchor onward so a retest of the projected
line counts, and spaced at least 3 bars from the last counted touch so one
consolidation cannot masquerade as several independent tests. Two genuine
touches minimum, and nothing fakes them: the anchors themselves are pivots on
the line, so every pair starts at two.

**Steepness earns nothing.** An earlier ATR-distance term rewarded steep lines
over better-fitting flat ones. Touches dominate, then span coverage, then
recency. A horizontal line is a legitimate trendline.
"""

from __future__ import annotations

import sys

from app.engines.bar import OHLCBar
from app.engines.geometry.types import Trendline, clamp_confidence, line_price_at_index
from app.engines.primitives.pivots import Pivot

__all__ = ["MAX_ANCHOR_AGE_BARS", "evaluate_trendline_candidates", "detect_trendlines"]

MIN_CANDLE_SEPARATION = 8
MIN_SCORE = 60
MIN_TOUCHES = 2
TOUCH_TOLERANCE_ATR = 0.15
#: Bars two counted touches must be apart to count as independent tests.
MIN_TOUCH_SPACING_BARS = 3
#: Closes may not pierce by more than this; wicks may pierce freely.
ENVELOPE_TOLERANCE_ATR = 0.25
#: The second anchor must be this recent, so a line belongs to the structure
#: currently on screen rather than one from another regime.
MAX_ANCHOR_AGE_BARS = 100
MAX_LINES_PER_SIDE = 2
#: A second line must sit meaningfully apart from an accepted one.
COLLINEAR_TOLERANCE_ATR = 0.5


def _count_pivot_touches(side_pivots: list[Pivot], a: Pivot, b: Pivot, atr: float) -> int:
    tol = max(atr * TOUCH_TOLERANCE_ATR, sys.float_info.epsilon)
    touches = 0
    last_counted = float("-inf")
    for pivot in side_pivots:
        if pivot.index < a.index:
            continue
        expected = line_price_at_index(a, b, pivot.index)
        if abs(pivot.price - expected) > tol:
            continue
        if pivot.index - last_counted < MIN_TOUCH_SPACING_BARS:
            continue
        touches += 1
        last_counted = pivot.index
    return touches


def _violates_envelope(bars: list[OHLCBar], a: Pivot, b: Pivot, side: str, atr: float) -> bool:
    tol = max(atr * ENVELOPE_TOLERANCE_ATR, sys.float_info.epsilon)
    for i in range(a.index, len(bars)):
        expected = line_price_at_index(a, b, i)
        close = bars[i].close
        if side == "low" and close < expected - tol:
            return True
        if side == "high" and close > expected + tol:
            return True
    return False


def _is_distinct_line(anchors: tuple[Pivot, Pivot], accepted: Trendline, atr: float) -> bool:
    tol = max(atr * COLLINEAR_TOLERANCE_ATR, sys.float_info.epsilon)
    a, b = accepted.anchors
    deviations = [abs(p.price - line_price_at_index(a, b, p.index)) for p in anchors]
    return max(deviations) > tol


def evaluate_trendline_candidates(
    bars: list[OHLCBar],
    side_pivots: list[Pivot],
    side: str,
    atr: float,
) -> list[Trendline]:
    """Every accepted pivot pair on one side, best first.

    Ordering is touch count first, then confidence, then recency — touches are
    lexicographically dominant by contract, so a three-touch flat line always
    beats a two-touch steep one.
    """
    if len(side_pivots) < 2 or atr <= 0 or not bars:
        return []

    last_index = len(bars) - 1
    candidates: list[Trendline] = []

    for i in range(len(side_pivots) - 1):
        for j in range(i + 1, len(side_pivots)):
            a = side_pivots[i]
            b = side_pivots[j]
            separation = b.index - a.index
            if separation < MIN_CANDLE_SEPARATION:
                continue

            anchor_age = last_index - b.index
            if anchor_age > MAX_ANCHOR_AGE_BARS:
                continue

            if _violates_envelope(bars, a, b, side, atr):
                continue

            touches = _count_pivot_touches(side_pivots, a, b, atr)
            if touches < MIN_TOUCHES:
                continue

            score = 40.0
            score += min(30, touches * 10)
            score += min(15, round(15 * separation / max(1, last_index)))
            score += max(0, 15 - round(15 * anchor_age / MAX_ANCHOR_AGE_BARS))
            if score < MIN_SCORE:
                continue

            candidates.append(
                Trendline(
                    side="support" if side == "low" else "resistance",
                    anchors=(a, b),
                    slope=(b.price - a.price) / max(1, separation),
                    touches=touches,
                    candle_separation=separation,
                    price_at_last_bar=line_price_at_index(a, b, last_index),
                    broken=False,
                    confidence=clamp_confidence(score),
                    evidence=[
                        f"{separation} bars separation",
                        f"{touches} pivot touches",
                        f"second anchor {anchor_age} bars ago",
                    ],
                )
            )

    candidates.sort(
        key=lambda line: (
            -line.touches,
            -line.confidence,
            -line.anchors[1].index,
            line.anchors[0].index,
        )
    )
    return candidates


def _detect_side(
    bars: list[OHLCBar], pivots: list[Pivot], side: str, atr: float
) -> list[Trendline]:
    side_pivots = [p for p in pivots if p.kind == ("low" if side == "low" else "high")]
    candidates = evaluate_trendline_candidates(bars, side_pivots, side, atr)

    accepted: list[Trendline] = []
    for candidate in candidates:
        if len(accepted) >= MAX_LINES_PER_SIDE:
            break
        if all(_is_distinct_line(candidate.anchors, line, atr) for line in accepted):
            accepted.append(candidate)
    return accepted


def detect_trendlines(bars: list[OHLCBar], pivots: list[Pivot], atr: float) -> list[Trendline]:
    """Top non-collinear envelope trendlines, both sides. Deterministic."""
    return _detect_side(bars, pivots, "low", atr) + _detect_side(bars, pivots, "high", atr)

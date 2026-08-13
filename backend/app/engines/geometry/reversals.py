"""Reversal templates over the zigzag: double extremes and head-and-shoulders.

Ported from AiChart's ``doubleExtremes.ts`` and ``headShoulders.ts``. Both scan
**newest window first** so the most recent formation wins — a double top from
two hundred bars ago is history, not a setup.

Both also resolve completion and invalidation *together* and let whichever
happened first decide. A shape that broke its neckline after price had already
run through the head is not a completed pattern; it is an invalidated one that
later moved. Checking only for completion would report the former.
"""

from __future__ import annotations

from collections.abc import Callable

from app.engines.bar import OHLCBar
from app.engines.geometry.pattern_state import (
    first_close_beyond,
    project_measured_move,
    state_confidence,
)
from app.engines.geometry.types import (
    PatternInstance,
    PatternStatus,
    PatternType,
    clamp_confidence,
)
from app.engines.primitives.pivots import Pivot

__all__ = ["detect_double_extremes", "detect_head_shoulders", "detect_triple_extremes"]

# --- double tops and bottoms -------------------------------------------------

#: The two extremes must be this close to each other to read as a double.
MAX_EXTREME_GAP_ATR = 0.4
MIN_BAR_SEPARATION = 8

# --- head and shoulders ------------------------------------------------------

MIN_HEAD_PROMINENCE_ATR = 0.8
MAX_SHOULDER_ASYMMETRY = 0.35

# --- triples -----------------------------------------------------------------

MAX_TRIPLE_SPREAD_ATR = 0.5


def _resolve(
    completion_broken: bool,
    completion_index: int | None,
    invalidation_broken: bool,
    invalidation_index: int | None,
) -> tuple[PatternStatus, int | None]:
    """Which break happened first, and on which bar.

    The bar travels with the status because the stage assessment needs it: a
    completion is only *confirmed* by follow-through on the bars after the
    break, and with no break bar there is nothing to look after.
    """
    if completion_broken and invalidation_broken:
        assert completion_index is not None and invalidation_index is not None
        if invalidation_index < completion_index:
            return PatternStatus.INVALIDATED, invalidation_index
        return PatternStatus.COMPLETED, completion_index
    if invalidation_broken:
        return PatternStatus.INVALIDATED, invalidation_index
    if completion_broken:
        return PatternStatus.COMPLETED, completion_index
    return PatternStatus.FORMING, None


def _scan_double(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float, variant: str
) -> PatternInstance | None:
    extreme_kind = "high" if variant == "top" else "low"

    for end in range(len(zigzag) - 1, 1, -1):
        second = zigzag[end]
        middle = zigzag[end - 1]
        first = zigzag[end - 2]
        if first.kind != extreme_kind or second.kind != extreme_kind or middle.kind == extreme_kind:
            continue
        if second.index - first.index < MIN_BAR_SEPARATION:
            continue
        if abs(second.price - first.price) > MAX_EXTREME_GAP_ATR * atr:
            continue

        neckline_price = middle.price
        extreme_price = (
            max(first.price, second.price) if variant == "top" else min(first.price, second.price)
        )
        height = abs(extreme_price - neckline_price)
        # Too shallow to be a reversal shape: a pair of highs a third of an ATR
        # apart is noise, not a double top.
        if not height > atr * 0.5:
            continue

        break_direction = "down" if variant == "top" else "up"
        completion = first_close_beyond(
            bars, second.index, _constant(neckline_price), break_direction, atr
        )
        invalidation = first_close_beyond(
            bars,
            second.index,
            _constant(extreme_price),
            "up" if variant == "top" else "down",
            atr,
        )
        status, break_index = _resolve(
            completion.broken,
            completion.break_index,
            invalidation.broken,
            invalidation.break_index,
        )

        base = (
            58
            + min(12, (height / atr) * 4)
            + min(
                10,
                (1 - abs(second.price - first.price) / (MAX_EXTREME_GAP_ATR * atr)) * 10,
            )
        )
        return PatternInstance(
            pattern_type=PatternType.DOUBLE_TOP if variant == "top" else PatternType.DOUBLE_BOTTOM,
            status=status,
            anchors=[first, middle, second],
            neckline=(
                (first.ts.timestamp(), neckline_price),
                (second.ts.timestamp(), neckline_price),
            ),
            projected_target=project_measured_move(neckline_price, height, break_direction),
            break_direction=break_direction,
            break_index=break_index,
            break_level=neckline_price,
            confidence=clamp_confidence(state_confidence(base, status)),
            evidence=[
                f"extremes {first.price:.5f}/{second.price:.5f}",
                f"gap={abs(second.price - first.price) / atr:.2f}atr",
                f"height={height / atr:.2f}atr",
            ],
        )
    return None


def detect_double_extremes(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float
) -> list[PatternInstance]:
    if atr <= 0 or len(zigzag) < 3:
        return []
    found = [_scan_double(bars, zigzag, atr, variant) for variant in ("top", "bottom")]
    return [pattern for pattern in found if pattern is not None]


def _scan_triple(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float, variant: str
) -> PatternInstance | None:
    """Three defended touches at the same level.

    Run alongside doubles rather than instead of them: on a chart with three
    touches the triple wins the overlap dedup because three defended touches
    score above two.
    """
    extreme_kind = "high" if variant == "top" else "low"

    for end in range(len(zigzag) - 1, 3, -1):
        window = zigzag[end - 4 : end + 1]
        if len(window) < 5:
            continue
        first, mid_a, second, mid_b, third = window
        if any(p.kind != extreme_kind for p in (first, second, third)):
            continue
        if mid_a.kind == extreme_kind or mid_b.kind == extreme_kind:
            continue

        prices = [first.price, second.price, third.price]
        spread = max(prices) - min(prices)
        if spread > MAX_TRIPLE_SPREAD_ATR * atr:
            continue

        neckline_price = (mid_a.price + mid_b.price) / 2
        extreme_price = max(prices) if variant == "top" else min(prices)
        height = abs(extreme_price - neckline_price)
        if not height > atr * 0.5:
            continue

        break_direction = "down" if variant == "top" else "up"
        completion = first_close_beyond(
            bars, third.index, _constant(neckline_price), break_direction, atr
        )
        invalidation = first_close_beyond(
            bars,
            third.index,
            _constant(extreme_price),
            "up" if variant == "top" else "down",
            atr,
        )
        status, break_index = _resolve(
            completion.broken,
            completion.break_index,
            invalidation.broken,
            invalidation.break_index,
        )

        base = (
            62
            + min(12, (height / atr) * 4)
            + min(8, (1 - spread / (MAX_TRIPLE_SPREAD_ATR * atr)) * 8)
        )
        return PatternInstance(
            pattern_type=PatternType.TRIPLE_TOP if variant == "top" else PatternType.TRIPLE_BOTTOM,
            status=status,
            anchors=[first, mid_a, second, mid_b, third],
            neckline=(
                (first.ts.timestamp(), neckline_price),
                (third.ts.timestamp(), neckline_price),
            ),
            projected_target=project_measured_move(neckline_price, height, break_direction),
            break_direction=break_direction,
            break_index=break_index,
            break_level=neckline_price,
            confidence=clamp_confidence(state_confidence(base, status)),
            evidence=[
                f"three touches spread={spread / atr:.2f}atr",
                f"height={height / atr:.2f}atr",
            ],
        )
    return None


def detect_triple_extremes(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float
) -> list[PatternInstance]:
    if atr <= 0 or len(zigzag) < 5:
        return []
    found = [_scan_triple(bars, zigzag, atr, variant) for variant in ("top", "bottom")]
    return [pattern for pattern in found if pattern is not None]


def _constant(level: float) -> Callable[[int], float]:
    """A fixed horizontal level, as the callable `first_close_beyond` expects."""

    def at(_index: int) -> float:
        return level

    return at


def _line_price_at_ts(a: Pivot, b: Pivot, ts: float) -> float:
    a_ts, b_ts = a.ts.timestamp(), b.ts.timestamp()
    if b_ts == a_ts:
        return a.price
    t = (ts - a_ts) / (b_ts - a_ts)
    return a.price + t * (b.price - a.price)


def _scan_head_shoulders(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float, inverse: bool
) -> PatternInstance | None:
    peak_kind = "low" if inverse else "high"

    for end in range(len(zigzag) - 1, 3, -1):
        window = zigzag[end - 4 : end + 1]
        if len(window) < 5:
            continue
        p1, t1, head, t2, p2 = window
        if any(p.kind != peak_kind for p in (p1, head, p2)):
            continue
        if t1.kind == peak_kind or t2.kind == peak_kind:
            continue

        sign = -1 if inverse else 1
        head_prominence = min(sign * (head.price - p1.price), sign * (head.price - p2.price))
        if head_prominence < MIN_HEAD_PROMINENCE_ATR * atr:
            continue

        head_height = abs(head.price - _line_price_at_ts(t1, t2, head.ts.timestamp()))
        if not head_height > 0:
            continue

        shoulder_gap = abs(p1.price - p2.price)
        if shoulder_gap > head_height * MAX_SHOULDER_ASYMMETRY:
            continue

        break_direction = "up" if inverse else "down"

        def neckline_at_index(index: int, a: Pivot = t1, b: Pivot = t2) -> float:
            if index < 0 or index >= len(bars):
                return float("nan")
            return _line_price_at_ts(a, b, bars[index].ts.timestamp())

        invalidation = first_close_beyond(
            bars,
            p2.index,
            _constant(head.price),
            "down" if inverse else "up",
            atr,
        )
        completion = first_close_beyond(bars, p2.index, neckline_at_index, break_direction, atr)
        status, break_index = _resolve(
            completion.broken,
            completion.break_index,
            invalidation.broken,
            invalidation.break_index,
        )

        break_level = (
            neckline_at_index(completion.break_index)
            if completion.break_index is not None
            else _line_price_at_ts(t1, t2, bars[-1].ts.timestamp())
        )

        base = (
            60
            + min(10, (head_prominence / atr) * 5)
            + min(10, (1 - shoulder_gap / (head_height or 1)) * 10)
        )
        return PatternInstance(
            pattern_type=(
                PatternType.INVERSE_HEAD_AND_SHOULDERS
                if inverse
                else PatternType.HEAD_AND_SHOULDERS
            ),
            status=status,
            anchors=[p1, t1, head, t2, p2],
            neckline=((t1.ts.timestamp(), t1.price), (t2.ts.timestamp(), t2.price)),
            projected_target=project_measured_move(break_level, head_height, break_direction),
            break_direction=break_direction,
            break_index=break_index,
            break_level=break_level,
            confidence=clamp_confidence(state_confidence(base, status)),
            evidence=[
                f"head_prominence={head_prominence / atr:.2f}atr",
                f"shoulder_asymmetry={shoulder_gap / head_height:.2f}",
                f"neckline {t1.price:.5f}->{t2.price:.5f}",
            ],
        )
    return None


def detect_head_shoulders(
    bars: list[OHLCBar], zigzag: list[Pivot], atr: float
) -> list[PatternInstance]:
    if atr <= 0 or len(zigzag) < 5:
        return []
    found = [_scan_head_shoulders(bars, zigzag, atr, inverse) for inverse in (False, True)]
    return [pattern for pattern in found if pattern is not None]

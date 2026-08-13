"""Japanese candlestick recognition.

The platform could name a head and shoulders but not an engulfing candle, so
the agent had to describe rejection and absorption in prose and could never
cite the single bar that made a zone worth trading.

**Everything here is ATR-relative, not absolute.** A "long" body is a different
number of pips on gold at 2,000 than it was on a major at 1.10, and a fixed
threshold finds hammers on every bar of one series and none of the other. The
volatility scale is what makes one rule work across regimes.

**Shape is named; meaning is not judged.** These functions answer "what is this
bar", not "is this a trade" — that is the decision engine's call. The one place
context enters is the prior move, and only because it is part of the *name*: a
hammer and a hanging man are the identical shape, and which one you are looking
at is decided entirely by what price did on the way in.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from app.core.numeric import js_round
from app.engines.bar import OHLCBar
from app.engines.geometry.types import CandlestickSignal

__all__ = ["DEFAULT_LOOKBACK", "DEFAULT_LIMIT", "detect_candlesticks"]

DOJI_BODY_ATR = 0.08
LONG_BODY_ATR = 0.6
LONG_WICK_RATIO = 2.0

DEFAULT_LOOKBACK = 30
#: Bounded like the rest of the snapshot: the last few bars are what a scalp is
#: entering on, and forty named candles is noise rather than evidence.
DEFAULT_LIMIT = 8

_TREND_SCALE = 0.0008
_TREND_LOOKBACK = 5


@dataclass(frozen=True, slots=True)
class _Parts:
    body: float
    upper: float
    lower: float
    range: float
    bullish: bool
    bearish: bool


def _parts(candle: OHLCBar) -> _Parts:
    body = abs(candle.close - candle.open)
    return _Parts(
        body=body,
        upper=max(0.0, candle.high - max(candle.open, candle.close)),
        lower=max(0.0, min(candle.open, candle.close) - candle.low),
        range=max(candle.high - candle.low, sys.float_info.epsilon),
        bullish=candle.close > candle.open,
        bearish=candle.close < candle.open,
    )


def _prior_trend(bars: list[OHLCBar], index: int, lookback: int = _TREND_LOOKBACK) -> str:
    """Short-term direction *into* a candle.

    Reversal shapes only mean something against a move they might reverse, so
    without this a hammer cannot be told from a hanging man, nor a star from a
    continuation.
    """
    start = max(0, index - lookback)
    if index - start < 2:
        return "flat"
    first = bars[start].close
    last = bars[index - 1].close
    move = last - first
    scale = abs(first) * _TREND_SCALE
    if move > scale:
        return "up"
    if move < -scale:
        return "down"
    return "flat"


def _clamp(value: float) -> int:
    return max(0, min(100, js_round(value)))


def detect_candlesticks(
    bars: list[OHLCBar],
    atr: float,
    *,
    lookback: int = DEFAULT_LOOKBACK,
    limit: int = DEFAULT_LIMIT,
) -> list[CandlestickSignal]:
    if len(bars) < 3 or not atr > 0:
        return []

    span = min(lookback, len(bars))
    start = max(2, len(bars) - span)
    signals: list[CandlestickSignal] = []

    def push(
        name: str,
        index: int,
        direction: str,
        strength: float,
        span_bars: int = 1,
        *evidence: str,
    ) -> None:
        signals.append(
            CandlestickSignal(
                name=name,
                index=index,
                ts=bars[index].ts.isoformat(),
                direction=direction,
                confidence=_clamp(strength),
                span_bars=span_bars,
                evidence=list(evidence),
            )
        )

    for i in range(start, len(bars)):
        c = bars[i]
        p = _parts(c)
        prev = bars[i - 1]
        prev_parts = _parts(prev)
        trend = _prior_trend(bars, i)

        # --- single-candle shapes (mutually exclusive by construction) ---
        if p.body <= atr * DOJI_BODY_ATR:
            push(
                "doji",
                i,
                "neutral",
                55 + (1 - p.body / (atr * DOJI_BODY_ATR)) * 25,
                1,
                f"body={p.body / atr:.3f}atr",
            )
        elif p.body >= atr * LONG_BODY_ATR and p.upper <= p.body * 0.1 and p.lower <= p.body * 0.1:
            push(
                "marubozu_bullish" if p.bullish else "marubozu_bearish",
                i,
                "bullish" if p.bullish else "bearish",
                70 + (p.body / atr) * 10,
                1,
                f"body={p.body / atr:.2f}atr, wicks<10% body",
            )
        elif p.body <= p.range * 0.35 and p.upper > p.body and p.lower > p.body:
            push("spinning_top", i, "neutral", 50, 1, "body<35% range, both wicks longer")

        # A hammer is defined by *proportion*, not by an absent opposite wick:
        # the lower shadow dominates the bar and the upper one is a fraction of
        # it. Requiring `upper <= body` missed almost every real hammer, whose
        # body is tiny by construction.
        long_lower = (
            p.lower >= p.body * LONG_WICK_RATIO
            and p.lower >= p.range * 0.5
            and p.upper <= p.lower * 0.35
        )
        long_upper = (
            p.upper >= p.body * LONG_WICK_RATIO
            and p.upper >= p.range * 0.5
            and p.lower <= p.upper * 0.35
        )

        if long_lower and p.body > atr * DOJI_BODY_ATR:
            # Same shape, opposite meaning by context.
            if trend == "down":
                push("hammer", i, "bullish", 60 + (p.lower / atr) * 12, 1, "after downmove")
            elif trend == "up":
                push("hanging_man", i, "bearish", 55 + (p.lower / atr) * 10, 1, "after upmove")
        if long_upper and p.body > atr * DOJI_BODY_ATR:
            if trend == "up":
                push("shooting_star", i, "bearish", 60 + (p.upper / atr) * 12, 1, "after upmove")
            elif trend == "down":
                push(
                    "inverted_hammer", i, "bullish", 55 + (p.upper / atr) * 10, 1, "after downmove"
                )

        # --- two-candle shapes ---
        engulfs_body = min(c.open, c.close) <= min(prev.open, prev.close) and max(
            c.open, c.close
        ) >= max(prev.open, prev.close)
        if engulfs_body and p.body > prev_parts.body and prev_parts.body > 0:
            if p.bullish and prev_parts.bearish:
                push("bullish_engulfing", i, "bullish", 65 + (p.body / atr) * 10, 2, "engulfs body")
            elif p.bearish and prev_parts.bullish:
                push("bearish_engulfing", i, "bearish", 65 + (p.body / atr) * 10, 2, "engulfs body")

        inside_prev_body = max(c.open, c.close) <= max(prev.open, prev.close) and min(
            c.open, c.close
        ) >= min(prev.open, prev.close)
        if inside_prev_body and prev_parts.body >= atr * 0.4 and p.body < prev_parts.body * 0.6:
            if prev_parts.bearish:
                push("bullish_harami", i, "bullish", 58, 2, "inside prior bearish body")
            elif prev_parts.bullish:
                push("bearish_harami", i, "bearish", 58, 2, "inside prior bullish body")

        tweezer_tol = atr * 0.1
        if abs(c.high - prev.high) <= tweezer_tol and trend == "up":
            push("tweezer_top", i, "bearish", 55, 2, "matched highs")
        if abs(c.low - prev.low) <= tweezer_tol and trend == "down":
            push("tweezer_bottom", i, "bullish", 55, 2, "matched lows")

        # --- three-candle shapes ---
        first = bars[i - 2]
        first_parts = _parts(first)
        small_middle = prev_parts.body <= first_parts.body * 0.5

        if (
            first_parts.bearish
            and small_middle
            and p.bullish
            and c.close > first.open - first_parts.body * 0.5
            and first_parts.body >= atr * 0.4
        ):
            push("morning_star", i, "bullish", 70, 3, "down, pause, recovery past midpoint")
        if (
            first_parts.bullish
            and small_middle
            and p.bearish
            and c.close < first.open + first_parts.body * 0.5
            and first_parts.body >= atr * 0.4
        ):
            push("evening_star", i, "bearish", 70, 3, "up, pause, decline past midpoint")

        three = (first, prev, c)
        bodies_real = all(abs(x.close - x.open) >= atr * 0.3 for x in three)
        if bodies_real:
            if (
                all(x.close > x.open for x in three)
                and prev.close > first.close
                and c.close > prev.close
            ):
                push("three_white_soldiers", i, "bullish", 72, 3, "three rising real bodies")
            if (
                all(x.close < x.open for x in three)
                and prev.close < first.close
                and c.close < prev.close
            ):
                push("three_black_crows", i, "bearish", 72, 3, "three falling real bodies")

    # Most recent first: a scalp cares about the bar it is entering on.
    signals.sort(key=lambda s: (-s.index, -s.confidence))
    return signals[:limit]

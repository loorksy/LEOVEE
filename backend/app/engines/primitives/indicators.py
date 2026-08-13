"""Technical indicators, ported from AiChart's ``src/lib/indicators.ts``.

Ported literally, including the choices that look odd:

- **EMA seeds with an SMA** of the first ``period`` values rather than the first
  value. Different seeds converge but never quite agree, and MACD is a
  difference of two EMAs, so a seed change moves the histogram sign near zero
  crossings — which is exactly where the signal is read.
- **RSI is Wilder's**, smoothed rather than a simple mean, and returns exactly
  100 when there are no losses in the window instead of dividing by zero.
- **Bollinger uses population σ** (divide by ``period``), matching charting
  applications rather than the sample σ a statistics library would default to.
- **Stochastic returns 50 on a flat window** rather than NaN, so a dead range
  does not poison a downstream comparison.

Each returns ``None`` rather than a partial value when there is not enough data.
A short series is a real condition on a 1-minute chart at the session open, and
an indicator that invents a number there is worse than one that abstains.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.engines.bar import OHLCBar

__all__ = [
    "MacdResult",
    "BollingerResult",
    "StochasticResult",
    "sma",
    "ema",
    "rsi",
    "macd",
    "bollinger",
    "stochastic",
    "atr",
    "adx",
    "directional_movement",
    "DirectionalMovement",
]


@dataclass(frozen=True, slots=True)
class MacdResult:
    macd: float
    signal: float
    histogram: float


@dataclass(frozen=True, slots=True)
class DirectionalMovement:
    adx: float
    plus_di: float
    minus_di: float
    #: |+DI - -DI|: how lopsided the directional pressure is.
    spread: float


@dataclass(frozen=True, slots=True)
class BollingerResult:
    upper: float
    middle: float
    lower: float
    #: Where the last close sits inside the band: 0 = lower, 1 = upper.
    percent_b: float
    #: Band width relative to the middle — a squeeze/expansion measure.
    width_pct: float


@dataclass(frozen=True, slots=True)
class StochasticResult:
    k: float
    d: float


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema(values: list[float], period: int) -> float | None:
    """Exponential moving average, seeded with the SMA of the first `period`."""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    prev = sum(values[:period]) / period
    for value in values[period:]:
        prev = value * k + prev * (1 - k)
    return prev


def rsi(values: list[float], period: int = 14) -> float | None:
    """Wilder's RSI in [0, 100]."""
    if len(values) < period + 1:
        return None
    gain = 0.0
    loss = 0.0
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gain += diff
        else:
            loss -= diff
    avg_gain = gain / period
    avg_loss = loss / period
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        up = diff if diff > 0 else 0.0
        down = -diff if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + up) / period
        avg_loss = (avg_loss * (period - 1) + down) / period
    if avg_loss == 0:
        # No losses in the window: RS is infinite, so RSI is exactly 100.
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(
    values: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> MacdResult | None:
    if len(values) < slow + signal_period:
        return None
    # A MACD-line *series* is built so the signal line can be an EMA of it —
    # the last value alone cannot be smoothed.
    macd_series: list[float] = []
    for i in range(slow, len(values) + 1):
        window = values[:i]
        fast_ema = ema(window, fast)
        slow_ema = ema(window, slow)
        if fast_ema is None or slow_ema is None:
            continue
        macd_series.append(fast_ema - slow_ema)
    if not macd_series:
        return None
    macd_line = macd_series[-1]
    signal = ema(macd_series, signal_period)
    if signal is None:
        return None
    return MacdResult(macd=macd_line, signal=signal, histogram=macd_line - signal)


def bollinger(values: list[float], period: int = 20, mult: float = 2) -> BollingerResult | None:
    if len(values) < period:
        return None
    window = values[-period:]
    middle = sum(window) / period
    # Population sigma, matching charting applications.
    variance = sum((v - middle) ** 2 for v in window) / period
    sd = math.sqrt(variance)
    upper = middle + mult * sd
    lower = middle - mult * sd
    last = values[-1]
    band = upper - lower
    return BollingerResult(
        upper=upper,
        middle=middle,
        lower=lower,
        percent_b=(last - lower) / band if band > 0 else 0.5,
        width_pct=band / abs(middle) if middle != 0 else 0.0,
    )


def stochastic(
    bars: list[OHLCBar],
    period_k: int = 14,
    smooth_k: int = 3,
    period_d: int = 3,
) -> StochasticResult | None:
    need = period_k + smooth_k + period_d - 2
    if len(bars) < need:
        return None
    raw_k: list[float] = []
    for i in range(period_k - 1, len(bars)):
        window = bars[i - period_k + 1 : i + 1]
        highest = max(bar.high for bar in window)
        lowest = min(bar.low for bar in window)
        span = highest - lowest
        # A perfectly flat window has no position to report; 50 is the neutral
        # answer rather than a division by zero.
        raw_k.append(((bars[i].close - lowest) / span) * 100 if span > 0 else 50.0)
    smoothed: list[float] = []
    for i in range(smooth_k - 1, len(raw_k)):
        window_k = raw_k[i - smooth_k + 1 : i + 1]
        smoothed.append(sum(window_k) / smooth_k)
    if len(smoothed) < period_d:
        return None
    k = smoothed[-1]
    d_window = smoothed[-period_d:]
    return StochasticResult(k=k, d=sum(d_window) / period_d)


def atr(bars: list[OHLCBar], period: int = 14) -> float | None:
    """Mean true range over the last `period` bars.

    A simple mean, not Wilder's smoothing — the reference uses the simple form
    for adaptive stops and sizing, and the two differ enough that swapping them
    silently changes every stop distance.
    """
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        current = bars[i]
        prev_close = bars[i - 1].close
        trs.append(
            max(
                current.high - current.low,
                abs(current.high - prev_close),
                abs(current.low - prev_close),
            )
        )
    window = trs[-period:]
    if not window:
        return None
    return sum(window) / len(window)


def adx(bars: list[OHLCBar], period: int = 14) -> float | None:
    """Wilder's ADX: trend *strength* in [0, 100], blind to direction."""
    full = directional_movement(bars, period)
    return full.adx if full is not None else None


def directional_movement(bars: list[OHLCBar], period: int = 14) -> DirectionalMovement | None:
    """ADX together with the +DI/-DI it is built from.

    Strength and direction come out of the same smoothing pass, and the regime
    classifier needs both: ADX says whether there *is* a trend, and the spread
    between the directional indices says which way. Recomputing them separately
    would run Wilder's smoothing twice over the same bars and invite the two
    answers to drift apart.

    Needs ``2 * period + 1`` bars: one span to seed the directional indices and
    another to seed the ADX average on top of them.
    """
    if len(bars) < 2 * period + 1:
        return None
    trs: list[float] = []
    plus_dms: list[float] = []
    minus_dms: list[float] = []
    for i in range(1, len(bars)):
        current = bars[i]
        prev = bars[i - 1]
        trs.append(
            max(
                current.high - current.low,
                abs(current.high - prev.close),
                abs(current.low - prev.close),
            )
        )
        up_move = current.high - prev.high
        down_move = prev.low - current.low
        plus_dms.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dms.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    last_plus_di = 0.0
    last_minus_di = 0.0
    sm_tr = sum(trs[:period])
    sm_plus = sum(plus_dms[:period])
    sm_minus = sum(minus_dms[:period])
    dxs: list[float] = []
    for i in range(period, len(trs)):
        sm_tr = sm_tr - sm_tr / period + trs[i]
        sm_plus = sm_plus - sm_plus / period + plus_dms[i]
        sm_minus = sm_minus - sm_minus / period + minus_dms[i]
        if sm_tr == 0:
            last_plus_di = last_minus_di = 0.0
            dxs.append(0.0)
            continue
        plus_di = (sm_plus / sm_tr) * 100
        minus_di = (sm_minus / sm_tr) * 100
        last_plus_di, last_minus_di = plus_di, minus_di
        di_sum = plus_di + minus_di
        dxs.append((abs(plus_di - minus_di) / di_sum) * 100 if di_sum > 0 else 0.0)

    if len(dxs) < period:
        return None
    value = sum(dxs[:period]) / period
    for i in range(period, len(dxs)):
        value = (value * (period - 1) + dxs[i]) / period
    di_sum = last_plus_di + last_minus_di
    return DirectionalMovement(
        adx=value,
        plus_di=last_plus_di,
        minus_di=last_minus_di,
        spread=abs(last_plus_di - last_minus_di) if di_sum > 0 else 0.0,
    )

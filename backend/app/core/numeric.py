"""JavaScript-compatible numeric helpers for the TypeScript → Python port.

The migration rewrites thousands of lines of deterministic trading geometry
from TypeScript into Python (docs/AICHART_MIGRATION_PLAN.md §5). Those two
languages agree on IEEE-754 doubles and disagree on almost everything built on
top of them. Each disagreement below produces a *plausible* wrong number rather
than a crash, which is the worst failure mode available: the port looks correct,
the goldens drift by a pip, and someone widens the tolerance to make it pass.

So the differences live here, named, tested, and used by the ported engines
instead of being rediscovered per file.

**Type policy.** Geometry, indicators, structure, liquidity, zones and regime
run on ``float`` — bit-identical to JavaScript's ``Number``, which is what the
reference implementation computed with. ``Decimal`` is reserved for the money
boundary: persisted entry/stop/target prices and risk sizing. Mixing the two
inside an engine reintroduces exactly the drift the golden fixtures exist to
catch.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any, Protocol

__all__ = [
    "js_round",
    "js_mod",
    "js_trunc_div",
    "to_float",
    "to_float_bars",
    "drop_none",
    "close_enough",
    "all_close",
]

# The porting tolerance. Anything needing looser than this is a port bug, not a
# tolerance case — see docs/PORTING.md.
DEFAULT_REL_TOL = 1e-9


def js_round(value: float) -> int:
    """``Math.round`` semantics: halves go up, toward +∞.

    Python's :func:`round` is banker's rounding — ``round(0.5) == 0`` and
    ``round(2.5) == 2`` — while JavaScript's ``Math.round(0.5) === 1`` and
    ``Math.round(-0.5) === -0`` (halves move toward positive infinity, not away
    from zero). Pivot indices and candle offsets are computed with this, so a
    half-pip difference silently shifts an anchor by one bar.
    """
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"js_round received a non-finite value: {value}")
    return math.floor(value + 0.5)


def js_mod(numerator: float, denominator: float) -> float:
    """``%`` semantics: the result takes the sign of the *numerator*.

    JavaScript truncates toward zero (``-7 % 3 === -1``); Python floors
    (``-7 % 3 == 2``). Timeframe bucketing and cyclical session arithmetic both
    hit negative numerators, where the two answers differ by a whole modulus.
    """
    if denominator == 0:
        return math.nan
    return math.fmod(numerator, denominator)


def js_trunc_div(numerator: float, denominator: float) -> int:
    """``Math.trunc(a / b)`` — truncation toward zero, not Python's floor.

    ``-7 // 2 == -4`` in Python but ``Math.trunc(-7 / 2) === -3``.
    """
    if denominator == 0:
        raise ZeroDivisionError("js_trunc_div by zero")
    return math.trunc(numerator / denominator)


def to_float(value: Any) -> float:
    """Coerce a DB ``Numeric``/``Decimal`` to the float the engines compute on.

    Crossing this boundary explicitly, in one place, is what keeps ``Decimal``
    from leaking into geometry and quietly changing results.
    """
    if isinstance(value, float):
        return value
    if isinstance(value, (int, Decimal)):
        return float(value)
    raise TypeError(f"cannot convert {type(value).__name__} to float")


class _HasOHLC(Protocol):
    open: Any
    high: Any
    low: Any
    close: Any


def to_float_bars(bars: Iterable[_HasOHLC]) -> list[tuple[float, float, float, float]]:
    """Flatten OHLC rows to plain float tuples for the deterministic engines."""
    return [
        (to_float(bar.open), to_float(bar.high), to_float(bar.low), to_float(bar.close))
        for bar in bars
    ]


def drop_none[T](value: T) -> T:
    """Recursively drop ``None``-valued mapping entries.

    ``JSON.stringify`` omits keys whose value is ``undefined``, so a golden
    fixture captured from the TypeScript reference simply has no key where the
    Python port has ``"key": null``. Without this the comparator reports a diff
    on every optional field that happens to be absent, and the real diffs get
    lost in the noise.
    """
    if isinstance(value, dict):
        return {k: drop_none(v) for k, v in value.items() if v is not None}  # type: ignore[return-value]
    if isinstance(value, list):
        return [drop_none(item) for item in value]  # type: ignore[return-value]
    return value


def close_enough(actual: float, expected: float, *, rel_tol: float = DEFAULT_REL_TOL) -> bool:
    """Float comparison for ported price arithmetic.

    NaN is treated as equal to NaN: the reference implementation uses NaN as a
    real "not computable here" value, and a golden fixture must be able to pin
    that rather than always failing on it.
    """
    if math.isnan(actual) and math.isnan(expected):
        return True
    return math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=0.0)


def all_close(
    actual: Sequence[float],
    expected: Sequence[float],
    *,
    rel_tol: float = DEFAULT_REL_TOL,
) -> bool:
    """Element-wise :func:`close_enough`, order and length significant."""
    if len(actual) != len(expected):
        return False
    return all(close_enough(a, e, rel_tol=rel_tol) for a, e in zip(actual, expected, strict=True))

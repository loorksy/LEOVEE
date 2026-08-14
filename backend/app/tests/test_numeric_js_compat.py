"""Pin the JavaScript semantics the ported engines rely on.

Each case below is a place where Python's built-in answer differs from the
TypeScript reference implementation's. The assertions are written against the
*JavaScript* result, with Python's own answer shown alongside so the difference
is visible rather than remembered.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from app.core.numeric import (
    all_close,
    close_enough,
    drop_none,
    js_mod,
    js_round,
    js_trunc_div,
    to_float,
    to_float_bars,
)

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.5, 1),  # Python's round() gives 0 — banker's rounding
        (1.5, 2),
        (2.5, 3),  # Python's round() gives 2
        (-0.5, 0),  # halves go toward +inf, so -0.5 rounds up to 0
        (-1.5, -1),  # Python's round() gives -2
        (-2.5, -2),
        (2.4, 2),
        (2.6, 3),
        (0.0, 0),
    ],
)
def test_js_round_matches_math_round(value: float, expected: int) -> None:
    assert js_round(value) == expected


def test_js_round_differs_from_python_round_on_halves() -> None:
    """If this ever stops differing, the helper has become pointless."""
    assert js_round(2.5) == 3
    assert round(2.5) == 2


def test_js_round_rejects_non_finite() -> None:
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            js_round(value)


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (7, 3, 1.0),
        (-7, 3, -1.0),  # Python's -7 % 3 == 2
        (7, -3, 1.0),  # Python's 7 % -3 == -2
        (-7, -3, -1.0),
        (5.5, 2, 1.5),
    ],
)
def test_js_mod_takes_the_sign_of_the_numerator(
    numerator: float, denominator: float, expected: float
) -> None:
    assert js_mod(numerator, denominator) == expected


def test_js_mod_differs_from_python_modulo_on_negatives() -> None:
    assert js_mod(-7, 3) == -1.0
    assert -7 % 3 == 2


def test_js_mod_by_zero_is_nan_not_an_exception() -> None:
    """JavaScript yields NaN; raising here would change control flow on a port."""
    assert math.isnan(js_mod(1, 0))


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (7, 2, 3),
        (-7, 2, -3),  # Python's -7 // 2 == -4
        (7, -2, -3),
        (6, 3, 2),
    ],
)
def test_js_trunc_div_truncates_toward_zero(
    numerator: float, denominator: float, expected: int
) -> None:
    assert js_trunc_div(numerator, denominator) == expected


def test_js_trunc_div_differs_from_floor_division() -> None:
    assert js_trunc_div(-7, 2) == -3
    assert -7 // 2 == -4


def test_to_float_accepts_decimal_and_int() -> None:
    assert to_float(Decimal("1.2345")) == pytest.approx(1.2345)
    assert to_float(3) == 3.0
    assert to_float(1.5) == 1.5
    with pytest.raises(TypeError):
        to_float("1.5")


def test_to_float_bars_flattens_decimal_rows() -> None:
    class Bar:
        def __init__(self) -> None:
            self.open = Decimal("1.10")
            self.high = Decimal("1.20")
            self.low = Decimal("1.05")
            self.close = Decimal("1.15")

    assert to_float_bars([Bar()]) == [(1.10, 1.20, 1.05, 1.15)]


def test_drop_none_removes_absent_optionals_recursively() -> None:
    """Mirrors JSON.stringify dropping `undefined` keys in the golden fixtures."""
    payload = {
        "kept": 1,
        "absent": None,
        "nested": {"kept": "x", "absent": None},
        "list": [{"absent": None, "kept": True}],
    }
    assert drop_none(payload) == {
        "kept": 1,
        "nested": {"kept": "x"},
        "list": [{"kept": True}],
    }


def test_drop_none_keeps_falsy_values() -> None:
    """Zero, empty string and False are real values, not absences."""
    assert drop_none({"a": 0, "b": "", "c": False, "d": None}) == {
        "a": 0,
        "b": "",
        "c": False,
    }


def test_close_enough_respects_the_porting_tolerance() -> None:
    assert close_enough(1.0, 1.0 + 1e-12)
    assert not close_enough(1.0, 1.0 + 1e-6)


def test_close_enough_treats_nan_as_equal_to_nan() -> None:
    """NaN is a real "not computable here" value the reference emits."""
    assert close_enough(math.nan, math.nan)
    assert not close_enough(math.nan, 1.0)


def test_all_close_is_order_and_length_significant() -> None:
    assert all_close([1.0, 2.0], [1.0, 2.0])
    assert not all_close([1.0, 2.0], [2.0, 1.0])
    assert not all_close([1.0], [1.0, 2.0])

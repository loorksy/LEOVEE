"""The comparator that guards every ported engine has to be right itself.

If `diff_against_golden` misses a difference, every port passes and the whole
method is theatre. So the cases below are mostly about what it must *not* let
through.
"""

from __future__ import annotations

import json

import pytest

from app.tests.golden import (
    diff_against_golden,
    golden_names,
    load_golden,
)

pytestmark = pytest.mark.no_db


def test_identical_structures_have_no_differences() -> None:
    payload = {"patterns": [{"type": "HEAD_SHOULDERS", "confidence": 72.5}]}
    assert diff_against_golden(payload, json.loads(json.dumps(payload))) == []


def test_price_within_tolerance_passes() -> None:
    assert diff_against_golden({"price": 1.10500000001}, {"price": 1.105}) == []


def test_price_outside_tolerance_is_reported() -> None:
    differences = diff_against_golden({"price": 1.1051}, {"price": 1.105})
    assert len(differences) == 1
    assert "price" in differences[0]


def test_categorical_values_must_match_exactly() -> None:
    """A near-miss on a pattern name is a different finding, not a rounding error."""
    differences = diff_against_golden({"type": "TRIANGLE"}, {"type": "WEDGE"})
    assert differences and "type" in differences[0]


def test_list_order_is_significant() -> None:
    """Detector output order encodes ranking, so a reorder is a real difference."""
    differences = diff_against_golden(
        {"pivots": [2, 1]},
        {"pivots": [1, 2]},
    )
    assert len(differences) == 2


def test_list_length_difference_is_reported() -> None:
    differences = diff_against_golden({"pivots": [1, 2, 3]}, {"pivots": [1, 2]})
    assert any("length" in d for d in differences)


def test_booleans_do_not_compare_equal_to_numbers() -> None:
    """bool is an int in Python: without care, `broken: True` would match `1`."""
    assert diff_against_golden({"broken": True}, {"broken": 1})
    assert diff_against_golden({"broken": False}, {"broken": 0})
    assert diff_against_golden({"broken": True}, {"broken": True}) == []


def test_absent_optional_matches_explicit_none() -> None:
    """JSON.stringify drops undefined keys, so the reference has no key at all."""
    assert diff_against_golden({"target": None, "kept": 1}, {"kept": 1}) == []


def test_missing_required_key_is_reported() -> None:
    differences = diff_against_golden({}, {"confidence": 61})
    assert differences and "missing" in differences[0]


def test_extra_key_is_reported() -> None:
    """A field the reference never produced is a divergence, not a bonus."""
    differences = diff_against_golden({"confidence": 61, "extra": 1}, {"confidence": 61})
    assert differences and "unexpected" in differences[0]


def test_type_mismatch_is_reported() -> None:
    assert diff_against_golden({"zones": {}}, {"zones": []})
    assert diff_against_golden({"zones": []}, {"zones": {}})


def test_all_differences_are_reported_not_just_the_first() -> None:
    """A port usually breaks one thing in several places; report them together."""
    differences = diff_against_golden(
        {"a": 1.5, "b": "X", "c": [1, 9]},
        {"a": 2.5, "b": "Y", "c": [1, 2]},
    )
    assert len(differences) == 3


def test_nested_paths_are_readable() -> None:
    differences = diff_against_golden(
        {"patterns": [{"anchors": [{"price": 1.2}]}]},
        {"patterns": [{"anchors": [{"price": 1.3}]}]},
    )
    assert differences[0].startswith("patterns[0].anchors[0].price")


def test_missing_fixture_explains_how_to_produce_it() -> None:
    with pytest.raises(FileNotFoundError) as caught:
        load_golden("geometry", "does-not-exist")
    message = str(caught.value)
    assert "PORTING.md" in message
    assert "hand-write" in message


def test_golden_names_is_empty_for_an_unported_engine() -> None:
    """Parametrising over an empty fixture set must not raise at collection."""
    assert golden_names("not-ported-yet") == []

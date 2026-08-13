"""Differential comparison against the TypeScript reference implementation.

Rewriting thousands of lines of trading geometry by reading it and writing the
Python equivalent produces silent drift: the code runs, the numbers are slightly
different, and nobody notices until a recommendation is wrong. Reviewing the
port more carefully does not fix this, because the errors are in arithmetic
nobody reads closely — an off-by-one window, a comparison that used ``>=``, a
rounding mode.

So the port is not trusted, it is pinned. AiChart's deterministic engines are
pure functions; their outputs on fixed candle fixtures are captured once, and
the Python port has to reproduce them.

**Tolerance policy** (docs/PORTING.md):

- discrete outputs — pattern type, direction, status, stage, ``broken``, pivot
  indices, array length **and order** — must match exactly;
- arithmetic-derived prices compare within ``1e-9`` relative;
- anything needing looser than that is a port bug, not a tolerance case.

The last rule is the one that matters. Widening a tolerance to make a test pass
converts a detectable defect into an undetectable one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.numeric import DEFAULT_REL_TOL, close_enough, drop_none

__all__ = [
    "GOLDEN_ROOT",
    "load_golden",
    "golden_names",
    "diff_against_golden",
    "assert_matches_golden",
]

GOLDEN_ROOT = Path(__file__).parent / "fixtures" / "golden"


def load_golden(engine: str, name: str) -> Any:
    """Load a captured reference output, or say precisely how to produce it."""
    path = GOLDEN_ROOT / engine / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"missing golden fixture {path}.\n"
            f"Capture it from the AiChart reference implementation (see "
            f"docs/PORTING.md), commit the JSON, and do not hand-write it — a "
            f"hand-written expectation pins the port to its own bugs."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def golden_names(engine: str) -> list[str]:
    """Fixture names available for an engine, for test parametrisation."""
    directory = GOLDEN_ROOT / engine
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def diff_against_golden(
    actual: Any,
    expected: Any,
    *,
    rel_tol: float = DEFAULT_REL_TOL,
    path: str = "",
) -> list[str]:
    """Every way `actual` departs from `expected`, as readable paths.

    Returns all differences rather than the first, because a port usually gets
    one thing wrong in several places and fixing them one failure at a time is
    needlessly slow.
    """
    differences: list[str] = []
    here = path or "<root>"

    # JSON.stringify omits undefined-valued keys, so the reference simply has no
    # key where the port may have an explicit null. Normalise before comparing.
    actual = drop_none(actual)
    expected = drop_none(expected)

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{here}: expected an object, got {type(actual).__name__}"]
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}" if path else key
            if key not in actual:
                differences.append(f"{child}: missing (reference has {expected[key]!r})")
            elif key not in expected:
                differences.append(f"{child}: unexpected (port has {actual[key]!r})")
            else:
                differences.extend(
                    diff_against_golden(actual[key], expected[key], rel_tol=rel_tol, path=child)
                )
        return differences

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{here}: expected a list, got {type(actual).__name__}"]
        if len(actual) != len(expected):
            # Order and length are significant: detector output order encodes
            # ranking, and a different count means a different set of findings.
            differences.append(f"{here}: length {len(actual)}, reference has {len(expected)}")
        for index, (a, e) in enumerate(zip(actual, expected, strict=False)):
            differences.extend(diff_against_golden(a, e, rel_tol=rel_tol, path=f"{path}[{index}]"))
        return differences

    if isinstance(expected, bool) or isinstance(actual, bool):
        # Checked before the numeric branch: bool is an int in Python, and
        # `True == 1` would let a boolean field silently compare equal to 1.
        if actual is not expected:
            differences.append(f"{here}: {actual!r}, reference has {expected!r}")
        return differences

    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not close_enough(float(actual), float(expected), rel_tol=rel_tol):
            differences.append(
                f"{here}: {actual!r}, reference has {expected!r} "
                f"(outside {rel_tol:g} relative tolerance)"
            )
        return differences

    if actual != expected:
        differences.append(f"{here}: {actual!r}, reference has {expected!r}")
    return differences


def assert_matches_golden(
    actual: Any,
    engine: str,
    name: str,
    *,
    rel_tol: float = DEFAULT_REL_TOL,
) -> None:
    expected = load_golden(engine, name)
    differences = diff_against_golden(actual, expected, rel_tol=rel_tol)
    if differences:
        raise AssertionError(
            f"{engine}/{name} does not reproduce the reference implementation "
            f"({len(differences)} difference(s)):\n  " + "\n  ".join(differences)
        )

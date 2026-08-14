"""The engine layer computes; it never asks a model.

AiChart's specialist agents mixed deterministic calculation with prompt
construction in one file, which is why porting them cleanly needed the two
halves separated. This guard keeps them separated.

A single `provider.complete()` inside `app/engines/**` costs more than it looks:
the engines stop being reproducible, the golden-fixture strategy stops working
(there is no golden output for a probabilistic call), every engine test needs a
provider double, and an engine that silently degrades on a rate limit starts
returning quietly different numbers instead of declining.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_db

ENGINES = Path(__file__).resolve().parents[2] / "engines"

#: Packages an engine must never reach into. Providers and services are the two
#: that matter: one makes the engine non-deterministic, the other makes it
#: depend on a database session and stop being a pure function of its bars.
FORBIDDEN_PREFIXES = (
    "app.providers",
    "app.services",
    "app.api",
    "app.workers",
    "app.agents",
)


def _engine_modules() -> list[Path]:
    return sorted(p for p in ENGINES.rglob("*.py") if "__pycache__" not in p.parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_the_engine_layer_exists_and_is_being_scanned() -> None:
    """A guard that silently scans nothing passes forever."""
    modules = _engine_modules()
    assert len(modules) >= 15, f"only {len(modules)} engine modules found — is the path right?"


@pytest.mark.parametrize("path", _engine_modules(), ids=lambda p: p.name)
def test_engines_import_nothing_from_the_llm_or_service_layers(path: Path) -> None:
    offending = sorted(
        name
        for name in _imports(path)
        if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_PREFIXES)
    )
    assert not offending, (
        f"{path.relative_to(ENGINES.parent)} imports {', '.join(offending)}. "
        "Engines are pure functions of their bars: keep prompt construction in "
        "app/agents/ and I/O in app/services/."
    )

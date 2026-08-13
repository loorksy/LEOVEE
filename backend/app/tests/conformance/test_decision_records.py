"""The decision records must stay in step with the files and the spec.

An ADR index that lists a record nobody wrote, or a record the index forgot, is
worse than no index: it is the same drift between documentation and reality that
produced the empty engine layer in the first place.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_db

REPO_ROOT = Path(__file__).resolve().parents[4]
ADR_DIR = REPO_ROOT / "docs" / "adr"
SPEC = REPO_ROOT / "LEOVEE_SPEC.md"


def _adr_files() -> list[Path]:
    return sorted(path for path in ADR_DIR.glob("*.md") if path.name != "README.md")


def test_adr_directory_exists_and_is_not_empty() -> None:
    assert _adr_files(), "docs/adr/ has no decision records"


def test_index_lists_every_record_and_no_others() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\((\d{4}-[a-z0-9-]+\.md)\)", index))
    on_disk = {path.name for path in _adr_files()}
    assert linked == on_disk, (
        f"docs/adr/README.md and the directory disagree — "
        f"only in index: {sorted(linked - on_disk)}, "
        f"only on disk: {sorted(on_disk - linked)}"
    )


@pytest.mark.parametrize("path", _adr_files(), ids=lambda p: p.stem)
def test_each_record_states_a_status_and_a_decision(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "**Status:**" in text, f"{path.name} has no status line"
    for heading in ("## Context", "## Decision", "## Consequences"):
        assert heading in text, f"{path.name} is missing {heading}"


def test_spec_carries_the_amendments_banner() -> None:
    """The spec must not read as though these decisions were never made."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "AMENDMENTS — READ BEFORE ANY SECTION BELOW" in spec
    assert "THIS TABLE WINS" in spec


def test_the_greenfield_rule_is_marked_superseded() -> None:
    """§0 is the instruction that caused the engine layer to be written blind."""
    spec = SPEC.read_text(encoding="utf-8")
    marker = spec.index("0. PROJECT IDENTITY")
    section = spec[marker : marker + 2000]
    assert "SUPERSEDED" in section, (
        "LEOVEE_SPEC.md §0 still reads as an active greenfield instruction"
    )

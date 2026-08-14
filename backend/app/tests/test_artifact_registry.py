"""The artifact taxonomy is a promise the frontend must be able to keep.

Every type resolves to a family that is a real renderer, no type maps to two
families, and the wide vocabulary the agent was given all resolves. A type that
resolved to a family with no renderer would be fabricated capability.
"""

from __future__ import annotations

import pytest

from app.agents.artifacts import ARTIFACT_FAMILIES, ARTIFACT_TYPES, family_for_type, parse_artifacts
from app.agents.artifacts.registry import _BY_FAMILY

pytestmark = pytest.mark.no_db

#: The vocabulary the agent is told it may emit (the owner's master list),
#: normalised. Every one must resolve to a real family.
_REQUESTED = [
    "ai-artifact-chart",
    "agent-candlestick-chart-artifact",
    "agent-trading-view-artifact",
    "agent-line-chart-artifact",
    "agent-invoice-artifact",
    "agent-contract-artifact",
    "agent-flowchart-artifact",
    "agent-sequence-diagram-artifact",
    "agent-python-script-artifact",
    "agent-sql-query-artifact",
    "agent-json-viewer-artifact",
    "agent-reasoning-trace-artifact",
    "agent-dashboard-artifact",
    "agent-pivot-table-artifact",
    "agent-order-book-artifact",
    "agent-kpi-scoreboard-artifact",
    "agent-loan-calculator-artifact",
    "agent-svg-illustration-artifact",
]


def test_every_family_has_at_least_one_type() -> None:
    for family in ARTIFACT_FAMILIES:
        assert _BY_FAMILY.get(family), family


def test_no_type_belongs_to_two_families() -> None:
    seen: dict[str, str] = {}
    for family, types in _BY_FAMILY.items():
        for t in types:
            assert t not in seen, f"{t} in both {seen.get(t)} and {family}"
            seen[t] = family


def test_every_declared_type_resolves_to_a_real_family() -> None:
    for t in ARTIFACT_TYPES:
        assert family_for_type(t) in ARTIFACT_FAMILIES


def test_the_requested_vocabulary_all_resolves() -> None:
    for raw in _REQUESTED:
        family = family_for_type(raw)
        assert family in ARTIFACT_FAMILIES, raw


def test_prefix_and_suffix_are_stripped() -> None:
    assert family_for_type("agent-line-chart-artifact") == "chart"
    assert family_for_type("line-chart-artifact") == "chart"
    assert family_for_type("line-chart") == "chart"


def test_an_unknown_type_degrades_to_markdown_not_a_wrong_renderer() -> None:
    assert family_for_type("agent-quantum-teleporter-artifact") == "markdown"


def test_a_wide_floor_of_types_is_available() -> None:
    # A floor, so a silent shrink of the vocabulary fails loudly.
    assert len(ARTIFACT_TYPES) >= 100


def test_parse_extracts_a_stamped_artifact() -> None:
    text = (
        "Here is the chart.\n\n"
        '```artifact\n{"type": "candlestick-chart", "title": "XAUUSD"}\n'
        '{"candles": []}\n```\n\nAnything else?'
    )
    artifacts = parse_artifacts(text)
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art["type"] == "candlestick-chart"
    assert art["family"] == "chart"
    assert art["title"] == "XAUUSD"
    assert '"candles"' in art["content"]


def test_a_malformed_header_keeps_the_payload_under_markdown() -> None:
    text = "```artifact\nnot json at all\nsome body\n```"
    artifacts = parse_artifacts(text)
    assert len(artifacts) == 1
    assert artifacts[0]["family"] == "markdown"
    assert "some body" in artifacts[0]["content"]


def test_text_without_a_fence_yields_no_artifacts() -> None:
    assert parse_artifacts("just a normal reply about gold") == []

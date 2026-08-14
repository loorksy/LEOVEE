"""Mechanical properties of the tool registry — the M11 exit criteria as code.

Like the RLS coverage guard, this walks the real registry rather than a list
kept by hand, so every tool added later is covered on the day it lands.
"""

from __future__ import annotations

import pytest

from app.agents.tools import TOOLS
from app.mcp.runtime import TOOL_ALIASES, TOOL_NAMES

pytestmark = pytest.mark.no_db

#: A floor, not a target: the registry shrinking below this means tools were
#: lost, and losing a tool must be a loud decision rather than a quiet diff.
MINIMUM_TOOL_COUNT = 30


def test_the_registry_holds_at_least_the_floor() -> None:
    assert len(TOOLS) >= MINIMUM_TOOL_COUNT, sorted(TOOLS)


def test_every_tool_declares_a_scope() -> None:
    for name, spec in TOOLS.items():
        assert spec.scope in ("platform", "workspace"), name


def test_every_tool_has_an_object_schema_and_a_description() -> None:
    for name, spec in TOOLS.items():
        assert spec.parameters.get("type") == "object", name
        assert isinstance(spec.parameters.get("properties", {}), dict), name
        assert spec.description.strip(), name


def test_no_tool_parameter_is_a_scope_id() -> None:
    """Workspace comes from the bound context. A parameter would be a hole:
    the caller could name a scope, and the tool would have to trust it."""
    for name, spec in TOOLS.items():
        properties = spec.parameters.get("properties", {})
        for forbidden in ("workspace_id", "tenant_id", "user_id"):
            assert forbidden not in properties, f"{name} accepts {forbidden}"


def test_aliases_resolve_and_never_shadow() -> None:
    for alias, canonical in TOOL_ALIASES.items():
        assert canonical in TOOLS, f"{alias} points at missing {canonical}"
        assert alias not in TOOLS, f"{alias} is both an alias and a tool"


def test_the_transport_surface_is_registry_plus_aliases_exactly() -> None:
    assert frozenset(TOOLS) | frozenset(TOOL_ALIASES) == TOOL_NAMES

"""Workspace record tools: the tenant's own recommendations, trades, journal.

Workspace-scoped — every handler reads through the RLS-bound session on the
context and none accepts a scope filter. Populated in M11; the registry merges
``TOOLS``.
"""

from __future__ import annotations

from app.agents.tools.registry import ToolSpec

TOOLS: tuple[ToolSpec, ...] = ()

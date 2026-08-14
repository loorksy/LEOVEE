"""Engine read tools: what the deterministic engines say about the market now.

Platform-scoped — these read shared candles and compute engine output; no
workspace rows are touched. Populated in M11; the registry merges ``TOOLS``.
"""

from __future__ import annotations

from app.agents.tools.registry import ToolSpec

TOOLS: tuple[ToolSpec, ...] = ()

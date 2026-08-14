"""Learning-loop read tools: strategy stats, calibration, case memory, DNA.

Mixed scope: strategy statistics, calibration and trading DNA are workspace
rows; market case memory is platform-global market fact (ADR: the two are
never added together). Populated in M11; the registry merges ``TOOLS``.
"""

from __future__ import annotations

from app.agents.tools.registry import ToolSpec

TOOLS: tuple[ToolSpec, ...] = ()

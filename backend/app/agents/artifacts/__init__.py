"""Chat artifacts: the agent's rich, typed outputs.

The agent emits an artifact as a fenced block in its reply:

    ```artifact
    {"type": "candlestick-chart", "title": "XAUUSD M15"}
    <payload>
    ```

One JSON header line, then the payload. The header names a *type* from a wide,
open-ended vocabulary; this package resolves that type to a small, closed set
of *families*, each of which is a real renderer on the frontend. Adding a new
type is one entry in ``registry.py`` — never a new component — which is the
same open-endedness rule the locale layer follows.

A type with no real renderer would be fabricated capability, so an unknown
type resolves to ``markdown`` (visible degrade), never to a family that
promises a render it cannot do.
"""

from app.agents.artifacts.registry import (
    ARTIFACT_FAMILIES,
    ARTIFACT_TYPES,
    ArtifactFamily,
    family_for_type,
    parse_artifacts,
    stamp_artifacts,
)

__all__ = [
    "ARTIFACT_FAMILIES",
    "ARTIFACT_TYPES",
    "ArtifactFamily",
    "family_for_type",
    "parse_artifacts",
    "stamp_artifacts",
]

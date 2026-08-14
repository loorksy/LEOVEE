"""The artifact taxonomy: a wide vocabulary resolved to a few real renderers.

Every ``type`` the agent may emit maps to exactly one ``family``. A family is a
renderer that actually exists on the frontend:

- ``markdown``  — prose, reports, letters, contracts, resumes, LaTeX, plans.
- ``table``     — anything tabular: sheets, CSV, pivots, matrices, grids.
- ``chart``     — quantitative visuals drawn by Recharts / lightweight-charts.
- ``mermaid``   — node/edge diagrams rendered by Mermaid.
- ``code``      — syntax-highlighted source, one language.
- ``json``      — an explorable JSON tree (logs, traces, datasets).
- ``web``       — a self-contained HTML document in a sandboxed iframe.

The lists below are grouped by family for readability; the map is derived from
them, and a conformance test asserts the derivation covers every declared type
and never collides. A type absent from every list resolves to ``markdown``.
"""

from __future__ import annotations

import json
from typing import Any, Literal

ArtifactFamily = Literal["markdown", "table", "chart", "mermaid", "code", "json", "web"]

ARTIFACT_FAMILIES: tuple[ArtifactFamily, ...] = (
    "markdown",
    "table",
    "chart",
    "mermaid",
    "code",
    "json",
    "web",
)

DEFAULT_FAMILY: ArtifactFamily = "markdown"

#: The `agent-…-artifact` prefix/suffix the agent may wrap a type in; stripped
#: so "agent-line-chart-artifact", "line-chart-artifact" and "line-chart" all
#: resolve identically.
_PREFIX = "agent-"
_SUFFIX = "-artifact"

_BY_FAMILY: dict[ArtifactFamily, tuple[str, ...]] = {
    "markdown": (
        "doc",
        "docx",
        "markdown",
        "latex",
        "report",
        "invoice",
        "contract",
        "resume",
        "pdf",
        "execution-plan",
        "typography-spec",
        "prompt-template",
    ),
    "table": (
        "sheet",
        "xlsx",
        "csv",
        "table",
        "datagrid",
        "pivot-table",
        "database-view",
        "parquet",
        "valuation-matrix",
        "budget-planner",
        "truth-table",
        "stock-screener",
        "order-book",
        "portfolio-summary",
        "evaluation-metric",
        "tax-calculator",
    ),
    "chart": (
        "chart",
        "ai-chart",
        "line-chart",
        "bar-chart",
        "pie-chart",
        "donut-chart",
        "candlestick-chart",
        "trading-view",
        "heatmap",
        "scatter-plot",
        "treemap",
        "sankey-diagram",
        "radar-chart",
        "funnel-chart",
        "gauge-chart",
        "area-chart",
        "waterfall-chart",
        "bubble-chart",
        "financial-model",
        "crypto-tracker",
        "kpi-scoreboard",
        "roi-calculator",
        "waveform",
    ),
    "mermaid": (
        "flowchart",
        "sequence-diagram",
        "architecture-diagram",
        "er-diagram",
        "mindmap",
        "class-diagram",
        "state-machine",
        "network-topology",
        "gantt-chart",
        "org-chart",
        "user-flow",
        "sitemap",
        "decision-tree",
        "git-workflow",
        "ci-cd-pipeline",
        "timeline",
    ),
    "code": (
        "python-script",
        "sql-query",
        "shell-script",
        "dockerfile",
        "k8s-manifest",
        "openapi-spec",
        "graphql-schema",
        "diff-patch",
        "regex-tester",
        "cron-builder",
        "react-component",
        "vue-component",
        "api-mock",
        "hash-generator",
        "base64-decoder",
        "jwt-debugger",
    ),
    "json": (
        "json-viewer",
        "dataset-viewer",
        "tool-call-log",
        "memory-log",
        "reasoning-trace",
        "embedding-cluster",
        "tokens-monitor",
    ),
    "web": (
        "html-page",
        "landing-page",
        "dashboard",
        "form-builder",
        "pricing-table",
        "modal-dialog",
        "kanban-board",
        "calendar-view",
        "stepper",
        "search-filter",
        "notification-center",
        "card-grid",
        "wireframe",
        "svg-icon",
        "svg-illustration",
        "canvas-drawing",
        "image-gallery",
        "3d-model-viewer",
        "audio-player",
        "video-player",
        "color-palette",
        "calculator",
        "loan-calculator",
        "unit-converter",
        "timezone-converter",
        "physics-simulation",
        "math-solver",
    ),
}

#: Every declared type, for the conformance floor.
ARTIFACT_TYPES: frozenset[str] = frozenset(t for types in _BY_FAMILY.values() for t in types)

_FAMILY_OF: dict[str, ArtifactFamily] = {
    t: family for family, types in _BY_FAMILY.items() for t in types
}


def _normalize(raw_type: str) -> str:
    t = raw_type.strip().lower()
    if t.startswith(_PREFIX):
        t = t[len(_PREFIX) :]
    if t.endswith(_SUFFIX):
        t = t[: -len(_SUFFIX)]
    return t


def family_for_type(raw_type: str) -> ArtifactFamily:
    """The renderer family for a type, defaulting to markdown for the unknown."""
    return _FAMILY_OF.get(_normalize(raw_type), DEFAULT_FAMILY)


_FENCE_OPEN = "```artifact"
_FENCE_CLOSE = "```"


def parse_artifacts(text: str) -> list[dict[str, Any]]:
    """Extract every artifact fence from an assistant message, in order.

    Mirrors the frontend streaming parser exactly. A malformed header keeps the
    payload under the markdown family rather than dropping the agent's output.
    """
    artifacts: list[dict[str, Any]] = []
    cursor = 0
    while True:
        open_at = text.find(_FENCE_OPEN, cursor)
        if open_at == -1:
            break
        header_start = text.find("\n", open_at)
        if header_start == -1:
            break
        header_end = text.find("\n", header_start + 1)
        if header_end == -1:
            break
        close_at = text.find(f"\n{_FENCE_CLOSE}", header_end)
        if close_at == -1:
            break
        header_line = text[header_start + 1 : header_end].strip()
        payload = text[header_end + 1 : close_at]
        artifacts.append(_build(header_line, payload))
        cursor = close_at + 1 + len(_FENCE_CLOSE)
    return artifacts


def _build(header_line: str, payload: str) -> dict[str, Any]:
    raw_type = "markdown"
    title: str | None = None
    language: str | None = None
    try:
        header = json.loads(header_line)
        if isinstance(header, dict):
            if isinstance(header.get("type"), str) and header["type"]:
                raw_type = header["type"]
            if isinstance(header.get("title"), str):
                title = header["title"]
            if isinstance(header.get("language"), str):
                language = header["language"]
    except (ValueError, TypeError):
        pass
    return {
        "type": _normalize(raw_type),
        "family": family_for_type(raw_type),
        "title": title,
        "language": language,
        "content": payload,
    }


def stamp_artifacts(text: str) -> list[dict[str, Any]]:
    """Parse and family-stamp artifacts for persistence in message content_json."""
    return parse_artifacts(text)

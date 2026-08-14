from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.agents.tools import TOOLS
from app.mcp.runtime import TOOL_ALIASES

_APPS_DIR = Path(__file__).resolve().parent / "apps"


def _apps_dirs() -> list[Path]:
    """Resolve ext-apps from monorepo root or Docker /app/ext-apps, then packaged apps."""
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "ext-apps",
        here.parents[2] / "ext-apps",  # docker: /app/app/mcp → /app/ext-apps
        here.parents[3] / "ext-apps",  # monorepo: backend/app/mcp → repo/ext-apps
    ]
    dirs: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate.is_dir() and candidate not in seen:
            dirs.append(candidate)
            seen.add(candidate)
    if _APPS_DIR not in seen:
        dirs.append(_APPS_DIR)
    return dirs


def list_tools() -> list[dict[str, Any]]:
    """The real registry definitions, plus the legacy dotted names as aliases.

    Descriptions and schemas come from the specs themselves — the placeholder
    strings this used to fabricate told a client nothing and could not drift
    less than the truth, only differently.
    """
    tools: list[dict[str, Any]] = [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.parameters,
            "scope": spec.scope,
        }
        for _, spec in sorted(TOOLS.items())
    ]
    tools.extend(
        {
            "name": alias,
            "alias_of": canonical,
            "description": TOOLS[canonical].description,
            "input_schema": TOOLS[canonical].parameters,
            "scope": TOOLS[canonical].scope,
        }
        for alias, canonical in sorted(TOOL_ALIASES.items())
    )
    return tools


def load_app_manifest(app_id: str) -> dict[str, Any]:
    for directory in _apps_dirs():
        path = directory / f"{app_id}.json"
        if path.is_file():
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return data
    raise FileNotFoundError(app_id)


def list_app_ids() -> list[str]:
    ids: set[str] = set()
    for directory in _apps_dirs():
        ids.update(p.stem for p in directory.glob("*.json"))
    return sorted(ids)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"--list-tools", "list-tools"}:
        print(json.dumps({"tools": list_tools()}, indent=2))
        return
    if len(sys.argv) > 1 and sys.argv[1] in {"--list-apps", "list-apps"}:
        print(json.dumps({"apps": list_app_ids()}, indent=2))
        return
    raise SystemExit(
        "leovee-mcp: use --list-tools or --list-apps. HTTP bridge: POST /api/v1/mcp/tools/invoke"
    )

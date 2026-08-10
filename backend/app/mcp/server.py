from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.mcp.runtime import TOOL_NAMES

_APPS_DIR = Path(__file__).resolve().parent / "apps"


def list_tools() -> list[dict[str, Any]]:
    return [{"name": name, "description": f"Leovee tool {name}"} for name in sorted(TOOL_NAMES)]


def load_app_manifest(app_id: str) -> dict[str, Any]:
    path = _APPS_DIR / f"{app_id}.json"
    if not path.is_file():
        raise FileNotFoundError(app_id)
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def list_app_ids() -> list[str]:
    return sorted(p.stem for p in _APPS_DIR.glob("*.json"))


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

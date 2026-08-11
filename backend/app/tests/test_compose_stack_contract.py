from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_compose_defines_leovee_mcp_and_metrics_edge() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    staging = (REPO_ROOT / "docker-compose.staging.yml").read_text(encoding="utf-8")
    caddy = (REPO_ROOT / "docker/caddy/Caddyfile").read_text(encoding="utf-8")

    assert "leovee-mcp:" in compose
    assert "docker/mcp.Dockerfile" in compose
    assert "leovee-mcp:" in staging
    assert "path /metrics" in caddy or "handle /metrics" in caddy
    assert "not remote_ip" in caddy
    assert "/api/v1/mcp/*" in caddy
    assert "leovee-mcp:8001" in caddy


def test_ext_apps_packaged_for_mcp_service() -> None:
    ext = REPO_ROOT / "ext-apps"
    assert (ext / "leovee-chart-app.json").is_file()
    assert (ext / "leovee-recommendation-app.json").is_file()

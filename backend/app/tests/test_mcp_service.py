from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.mcp.http_app import create_mcp_app
from app.mcp.server import list_app_ids, load_app_manifest


def test_ext_apps_manifests_have_csp_and_workspace_binding() -> None:
    ids = list_app_ids()
    assert "leovee-chart-app" in ids
    assert "leovee-recommendation-app" in ids
    for app_id in ("leovee-chart-app", "leovee-recommendation-app"):
        manifest = load_app_manifest(app_id)
        csp = manifest["contentSecurityPolicy"]
        assert "default-src" in csp
        assert "frame-ancestors" in csp
        assert manifest.get("security", {}).get("workspaceBound") is True
        assert manifest.get("security", {}).get("denyCrossWorkspace") is True
        assert manifest.get("api", {}).get("auth") == "bearer"


async def test_mcp_sidecar_app_exposes_tools_and_manifest() -> None:
    application = create_mcp_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health/live")
        tools = await client.get("/api/v1/mcp/tools")
        apps = await client.get("/api/v1/mcp/apps")
        manifest = await client.get("/api/v1/mcp/apps/leovee-chart-app/manifest")
    assert live.status_code == 200
    assert tools.status_code == 200
    assert "tools" in tools.json()
    assert apps.status_code == 200
    assert "leovee-chart-app" in apps.json()["items"]
    assert manifest.status_code == 200
    assert "Content-Security-Policy" in manifest.headers

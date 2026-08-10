from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "script",
    [
        "scripts/migrate.sh",
        "scripts/backup_pg.sh",
        "scripts/restore_pg.sh",
    ],
)
def test_deployment_scripts_support_dry_run(script: str) -> None:
    path = REPO_ROOT / script
    result = subprocess.run(
        ["bash", str(path), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "dry-run" in result.stdout.lower()


def test_migrate_script_exists_and_is_executable() -> None:
    migrate = REPO_ROOT / "scripts" / "migrate.sh"
    assert migrate.is_file()
    assert migrate.stat().st_mode & 0o111


@pytest.mark.asyncio
async def test_health_startup_endpoint_for_probes() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
        startup = await client.get("/health/startup")
    assert live.json()["status"] == "ok"
    assert "checks" in ready.json()
    assert startup.json()["status"] == "ok"
    assert "migrations" in startup.json()

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_liveness() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_reports_infra_checks() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    db_check = body["checks"]["database"]
    if db_check.get("skipped"):
        assert body["status"] == "ok"
    elif db_check.get("ok"):
        assert body["status"] == "ok"
    else:
        assert body["status"] == "degraded"
        assert db_check.get("error")

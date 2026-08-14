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
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    db_check = body["checks"]["database"]
    if db_check.get("skipped") or db_check.get("ok"):
        assert body["status"] == "ok"
        # Healthy readiness is a 200.
        assert response.status_code == 200
    else:
        assert body["status"] == "degraded"
        assert db_check.get("error")
        # Degraded readiness is a 503 so a load balancer pulls the instance
        # from rotation rather than routing DB-backed requests it cannot serve.
        assert response.status_code == 503

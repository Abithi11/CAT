"""Smoke suite — promised in the submission: services up, endpoints healthy."""


async def _register(client, slug="smokeco"):
    reg = await client.post("/auth/register", json={
        "tenant_name": slug.title(), "tenant_slug": slug,
        "email": f"admin@{slug}.com", "password": "smoketest123",
    })
    assert reg.status_code == 201, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


class TestSmoke:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_openapi_lists_every_feature_surface(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json()["paths"]
        for expected in [
            "/health", "/auth/login", "/auth/register", "/rentals/checkout",
            "/rentals/checkin", "/usage", "/seed", "/rentals/detect-overdue",
            "/analytics/anomalies", "/dashboard/summary", "/dashboard/live-assets",
            "/alerts", "/alerts/scan", "/reports/summary", "/forecast",
            "/forecast/rebalancing", "/degradation/fleet", "/degradation/validate",
            "/agent/investigate", "/agent/cases", "/agent/demo-replay",
            "/equipment", "/equipment/{equipment_id}/immobilize",
            "/equipment/{equipment_id}/qrcode",
        ]:
            assert expected in paths, f"missing route: {expected}"

    async def test_auth_roundtrip(self, client):
        headers = await _register(client, "authco")
        login = await client.post("/auth/login", json={
            "tenant_slug": "authco", "email": "admin@authco.com", "password": "smoketest123",
        })
        assert login.status_code == 200
        me = await client.get("/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "admin@authco.com"

    async def test_all_read_endpoints_healthy_on_empty_tenant(self, client):
        headers = await _register(client)
        for path in [
            "/dashboard/summary", "/dashboard/live-assets", "/analytics/anomalies",
            "/alerts", "/reports/summary", "/forecast", "/forecast/rebalancing",
            "/degradation/fleet", "/agent/cases", "/agent/demo-replay", "/equipment",
        ]:
            resp = await client.get(path, headers=headers)
            assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"

    async def test_endpoints_require_auth(self, client):
        for path in ["/dashboard/summary", "/alerts", "/forecast", "/degradation/fleet"]:
            resp = await client.get(path)
            assert resp.status_code in (401, 403), f"{path} should require auth"

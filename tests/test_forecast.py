"""Demand forecasting (NGBoost distributions) + rebalancing recommendations."""


async def _seeded_tenant(client, slug, months=12, equipment=10):
    reg = await client.post("/auth/register", json={
        "tenant_name": slug.title(), "tenant_slug": slug,
        "email": f"fc@{slug}.com", "password": "forecast123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seed = await client.post("/seed", json={
        "seed": 42, "num_equipment": equipment, "num_sites": 3,
        "num_operators": 5, "months": months,
    }, headers=headers)
    assert seed.status_code == 201
    return headers


class TestForecast:
    async def test_forecast_returns_probability_distributions(self, client, engine):
        headers = await _seeded_tenant(client, "fcco")
        resp = await client.get("/forecast?horizon_months=2", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] in ("ngboost", "seasonal_baseline")
        assert data["rows"], "seeded tenant must produce forecast rows"
        for row in data["rows"]:
            assert row["expected_rentals"] >= 0
            assert row["p10"] <= row["expected_rentals"] <= row["p90"]
            for k, p in row["prob_at_least"].items():
                assert 0.0 <= p <= 1.0, f"prob_at_least[{k}]={p}"
            assert row["site_code"] and row["equipment_type"] and row["month"]

    async def test_rebalancing_carries_rupee_savings(self, client, engine):
        headers = await _seeded_tenant(client, "rebalco")
        resp = await client.get("/forecast/rebalancing", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "recommendations" in data
        total = 0
        for rec in data["recommendations"]:
            assert rec["monthly_savings_inr"] > 0
            assert rec["equipment_code"] and rec["move_to_site"]
            assert "₹" in rec["rationale"]
            total += rec["monthly_savings_inr"]
        assert data["total_monthly_savings_inr"] == total

    async def test_forecast_on_empty_tenant_degrades_gracefully(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "EmptyFc", "tenant_slug": "emptyfc",
            "email": "fc@emptyfc.com", "password": "forecast123",
        })
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
        resp = await client.get("/forecast", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["rows"] == []
        assert resp.json()["model"] == "none"

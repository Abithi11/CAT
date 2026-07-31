"""Functional suite — promised in the submission: the full lifecycle
checkout -> usage accumulation -> overdue alert -> anomaly flag -> degradation trace."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import numpy as np
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.equipment import Equipment
from models.operator import Operator
from models.rental import Rental
from models.site import Site
from models.tenant import Tenant

HISTORY_DAYS = 150
ONSET_AGO = 60  # planted degradation onset: 60 days before today
TOLERANCE_DAYS = 30


class TestFullLifecycle:
    @pytest.fixture
    async def setup(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "LifeCo", "tenant_slug": "lifeco",
            "email": "ops@lifeco.com", "password": "lifecycle123",
        })
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "lifeco"))).scalar_one()
            site = Site(id=uuid4(), tenant_id=tenant.id, site_code="S-E2E",
                        name="E2E Quarry", location="Pune")
            op = Operator(id=uuid4(), tenant_id=tenant.id, operator_code="OP-E2E", name="E2E Operator")
            deg = Equipment(id=uuid4(), tenant_id=tenant.id,
                            equipment_code="DEG-EX-1", equipment_type="Excavator")
            bad = Equipment(id=uuid4(), tenant_id=tenant.id,
                            equipment_code="BAD-CR-2", equipment_type="Crane")
            db.add_all([site, op, deg, bad])
            await db.commit()
            return {"headers": headers, "factory": factory,
                    "site_id": str(site.id), "op_id": str(op.id),
                    "deg_id": str(deg.id), "bad_id": str(bad.id)}

    async def test_checkout_usage_overdue_anomaly_degradation(self, client, setup):
        headers = setup["headers"]
        today = date.today()

        # --- 1. CHECKOUT (QR-simulated, via API) ---
        resp = await client.post("/rentals/checkout", json={
            "equipment_code": "DEG-EX-1",
            "site_id": setup["site_id"], "operator_id": setup["op_id"],
            "expected_return_date": str(today + timedelta(days=30)),
        }, headers=headers)
        assert resp.status_code == 201, resp.text
        deg_rental_id = resp.json()["id"]

        # Backdate the rental so it covers the machine's usage history
        async with setup["factory"]() as db:
            await db.execute(update(Rental).where(Rental.id == UUID(deg_rental_id))
                             .values(check_out_date=today - timedelta(days=HISTORY_DAYS)))
            await db.commit()

        # --- 2. USAGE ACCUMULATION with a hidden degradation onset ---
        # Healthy fuel rate ~12 L/engine-hour; from ONSET_AGO days back the
        # machine drifts +0.4%/day — exactly the failure mode the tracer hunts.
        rng = np.random.default_rng(7)
        onset_date = today - timedelta(days=ONSET_AGO)
        for i in range(HISTORY_DAYS):
            log_day = today - timedelta(days=HISTORY_DAYS - i)
            drift_days = (log_day - onset_date).days
            mult = 1.0 + 0.004 * max(0, drift_days)
            engine_h = float(7.0 + rng.uniform(-1.0, 1.0))
            fuel = engine_h * 12.0 * mult * float(rng.uniform(0.97, 1.03))
            resp = await client.post("/usage", json={
                "equipment_code": "DEG-EX-1", "log_date": str(log_day),
                "engine_hours": round(engine_h, 2), "idle_hours": 1.0,
                "fuel_litres": round(fuel, 2),
            }, headers=headers)
            assert resp.status_code == 201, resp.text

        # --- 3. A second machine goes overdue with untraceable, idle-heavy usage ---
        resp = await client.post("/rentals/checkout", json={
            "equipment_code": "BAD-CR-2",
            "expected_return_date": str(today - timedelta(days=5)),  # already overdue
        }, headers=headers)
        assert resp.status_code == 201, resp.text
        for i in range(10):
            resp = await client.post("/usage", json={
                "equipment_code": "BAD-CR-2", "log_date": str(today - timedelta(days=i + 1)),
                "engine_hours": 0.5, "idle_hours": 11.0, "fuel_litres": 4.0,
            }, headers=headers)
            assert resp.status_code == 201, resp.text

        # --- 4. OVERDUE ALERT fires (same scan APScheduler runs) ---
        scan = await client.post("/alerts/scan", headers=headers)
        assert scan.status_code == 200, scan.text
        assert scan.json()["created"] >= 1
        alerts = (await client.get("/alerts?status=open", headers=headers)).json()
        overdue_alerts = [a for a in alerts if a["alert_type"] == "overdue"]
        assert any("BAD-CR-2" in a["message"] for a in overdue_alerts), alerts

        # --- 5. ANOMALY FLAG on the ghost/idle machine ---
        anomalies = (await client.get("/analytics/anomalies", headers=headers)).json()
        by_code = {a["equipment_code"]: a for a in anomalies}
        assert by_code["BAD-CR-2"]["anomaly_score"] >= 60
        assert by_code["BAD-CR-2"]["severity"] == "Critical Anomaly"

        # --- 6. DEGRADATION TRACE finds the onset and the custody period ---
        trace = (await client.get(f"/equipment/{setup['deg_id']}/degradation",
                                  headers=headers)).json()
        assert trace["onset_detected"], trace["metrics"]
        detected = date.fromisoformat(trace["onset_date"])
        error_days = abs((detected - onset_date).days)
        assert error_days <= TOLERANCE_DAYS, (
            f"onset {detected} vs planted {onset_date} — off by {error_days}d")
        custody = trace["custody_at_onset"]
        assert custody is not None
        assert custody["rental_id"] == deg_rental_id
        assert custody["site_code"] == "S-E2E"
        assert custody["operator_code"] == "OP-E2E"
        assert trace["estimated_savings_inr"] > 0
        assert len(trace["timeline"]) >= HISTORY_DAYS - 5

        # --- 7. Dashboard reflects the whole story ---
        summary = (await client.get("/dashboard/summary", headers=headers)).json()
        assert summary["fleet_overview"]["status_counts"]["overdue"] >= 1
        assert summary["alerts_summary"]["overdue_rentals_count"] >= 1
        assert summary["alerts_summary"]["critical_anomalies_count"] >= 1

        # --- 8. The overdue machine can still be returned ---
        checkin = await client.post("/rentals/checkin", json={"equipment_code": "BAD-CR-2"},
                                    headers=headers)
        assert checkin.status_code == 200, checkin.text
        assert checkin.json()["status"] == "returned"

"""Tests for overdue detection and NumPy anomaly scoring analytics."""

from datetime import date, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.equipment import Equipment
from models.rental import Rental
from models.site import Site
from models.operator import Operator
from models.tenant import Tenant
from models.usage_log import UsageLog


class TestAnalytics:
    @pytest.fixture
    async def analytics_setup(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "AnomCo", "tenant_slug": "anomco",
            "email": "admin@anomco.com", "password": "securepassword",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            from sqlalchemy import select
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "anomco"))).scalar_one()

            # 1. Create equipment for overdue testing
            eq_overdue = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="OV-101", equipment_type="Excavator", status="rented")
            rental_overdue = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq_overdue.id,
                check_out_date=date.today() - timedelta(days=20),
                expected_return_date=date.today() - timedelta(days=5),  # 5 days overdue!
                status="active"
            )

            # 2. Create equipment with severe anomalies (High Idle + NULL Site/Op)
            eq_anom = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="BAD-202", equipment_type="Crane", status="rented")
            rental_anom = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq_anom.id,
                check_out_date=date.today() - timedelta(days=10),
                expected_return_date=date.today() + timedelta(days=10),
                status="active"
            )

            # 3. Create normal equipment
            eq_norm = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="GOOD-303", equipment_type="Crane", status="rented")
            site = Site(id=uuid4(), tenant_id=tenant.id, site_code="S-88", name="Valid Site", location="Chennai")
            op = Operator(id=uuid4(), tenant_id=tenant.id, operator_code="OP-88", name="Valid Op")
            rental_norm = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq_norm.id,
                site_id=site.id, operator_id=op.id,
                check_out_date=date.today() - timedelta(days=10),
                expected_return_date=date.today() + timedelta(days=10),
                status="active"
            )

            db.add_all([eq_overdue, rental_overdue, eq_anom, rental_anom, eq_norm, rental_norm, site, op])
            await db.flush()

            # Log 5 days of extreme idling with NO site and NO operator (ghost rental + waste) for BAD-202
            for i in range(5):
                log_day = date.today() - timedelta(days=i+1)
                db.add(UsageLog(
                    id=uuid4(), tenant_id=tenant.id, rental_id=rental_anom.id, equipment_id=eq_anom.id,
                    log_date=log_day, engine_hours=1.0, idle_hours=11.0, fuel_litres=50.0,
                    site_id=None, operator_id=None
                ))

            # Log clean, efficient usage for GOOD-303
            for i in range(5):
                log_day = date.today() - timedelta(days=i+1)
                db.add(UsageLog(
                    id=uuid4(), tenant_id=tenant.id, rental_id=rental_norm.id, equipment_id=eq_norm.id,
                    log_date=log_day, engine_hours=8.0, idle_hours=0.5, fuel_litres=60.0,
                    site_id=site.id, operator_id=op.id
                ))

            await db.commit()
            return {"headers": headers}

    async def test_overdue_detection_endpoint(self, client, analytics_setup):
        setup = analytics_setup
        resp = await client.post("/rentals/detect-overdue", headers=setup["headers"])
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["overdue"]) >= 1
        overdue_codes = [x["equipment_code"] for x in data["overdue"]]
        assert "OV-101" in overdue_codes

    async def test_overdue_detection_idempotent(self, client, analytics_setup):
        """A flagged rental must keep appearing in every scan until checked in."""
        setup = analytics_setup
        first = await client.post("/rentals/detect-overdue", headers=setup["headers"])
        second = await client.post("/rentals/detect-overdue", headers=setup["headers"])
        for resp in (first, second):
            assert resp.status_code == 200, resp.text
            codes = [x["equipment_code"] for x in resp.json()["overdue"]]
            assert "OV-101" in codes

    async def test_anomalies_endpoint(self, client, analytics_setup):
        setup = analytics_setup
        resp = await client.get("/analytics/anomalies?window_days=30", headers=setup["headers"])
        assert resp.status_code == 200, resp.text
        results = resp.json()

        assert len(results) >= 3
        by_code = {item["equipment_code"]: item for item in results}

        bad = by_code["BAD-202"]
        good = by_code["GOOD-303"]

        assert bad["anomaly_score"] >= 60
        assert bad["severity"] == "Critical Anomaly"
        assert "High underutilization" in bad["explanation"] or "Untraceable operations" in bad["explanation"]
        assert bad["metrics"]["idle_ratio"] > 0.5
        assert bad["metrics"]["ghost_ratio"] == 1.0

        assert good["anomaly_score"] < 35
        assert good["severity"] == "Normal"
        assert good["metrics"]["ghost_ratio"] == 0.0

    async def test_structural_rule_escalates_ghost_usage_to_critical(self, client, engine):
        """Fully untraceable custody must reach Critical even when the machine
        works normally otherwise: 45*idle + 40*ghost caps at ~57 for that shape,
        which would silently keep a governance failure off the alert feed."""
        reg = await client.post("/auth/register", json={
            "tenant_name": "GhostCo", "tenant_slug": "ghostco",
            "email": "ops@ghostco.com", "password": "ghost123",
        })
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "ghostco"))).scalar_one()
            eq = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="GHOST-1",
                           equipment_type="Loader", status="rented")
            rental = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq.id,
                check_out_date=date.today() - timedelta(days=12),
                expected_return_date=date.today() + timedelta(days=12),
                status="active",
            )
            db.add_all([eq, rental])
            await db.flush()
            # Healthy work pattern (idle ratio ~0.33) but zero custody records
            for i in range(10):
                db.add(UsageLog(
                    id=uuid4(), tenant_id=tenant.id, rental_id=rental.id, equipment_id=eq.id,
                    log_date=date.today() - timedelta(days=i + 1),
                    engine_hours=6.0, idle_hours=3.0, fuel_litres=66.0,
                    site_id=None, operator_id=None,
                ))
            await db.commit()

        resp = await client.get("/analytics/anomalies?window_days=30", headers=headers)
        ghost = {i["equipment_code"]: i for i in resp.json()}["GHOST-1"]
        assert ghost["metrics"]["ghost_ratio"] == 1.0
        assert ghost["metrics"]["idle_ratio"] < 0.5, "idle alone must not explain the score"
        assert ghost["anomaly_score"] >= 60, ghost
        assert ghost["severity"] == "Critical Anomaly"
        assert "Structural violation" in ghost["explanation"]

    async def test_anomalies_min_score_filter(self, client, analytics_setup):
        setup = analytics_setup
        resp = await client.get("/analytics/anomalies?min_score=60", headers=setup["headers"])
        assert resp.status_code == 200
        results = resp.json()
        for item in results:
            assert item["anomaly_score"] >= 60

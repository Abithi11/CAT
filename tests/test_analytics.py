"""Tests for overdue detection and NumPy anomaly scoring analytics."""

from datetime import date, timedelta
from uuid import uuid4
import pytest
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

    async def test_anomalies_min_score_filter(self, client, analytics_setup):
        setup = analytics_setup
        resp = await client.get("/analytics/anomalies?min_score=60", headers=setup["headers"])
        assert resp.status_code == 200
        results = resp.json()
        for item in results:
            assert item["anomaly_score"] >= 60

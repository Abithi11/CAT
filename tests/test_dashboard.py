"""Tests for Live Asset Dashboard & Summary endpoints."""

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


class TestDashboard:
    @pytest.fixture
    async def dashboard_setup(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "DashCo", "tenant_slug": "dashco",
            "email": "ceo@dashco.com", "password": "securepassword",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            from sqlalchemy import select
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "dashco"))).scalar_one()

            # Create sites and equipment
            site_a = Site(id=uuid4(), tenant_id=tenant.id, site_code="SITE-10", name="Apex Quarry", location="Goa")
            op_a = Operator(id=uuid4(), tenant_id=tenant.id, operator_code="OP-10", name="Operator A")
            
            eq_1 = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="DASH-EX-1", equipment_type="Excavator", status="rented")
            eq_2 = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="DASH-CR-2", equipment_type="Crane", status="available")
            # Overdue machine: equipment stays "rented" (production never sets an
            # "overdue" equipment status) — overdueness lives on the open rental.
            eq_3 = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="DASH-BD-3", equipment_type="Bulldozer", status="rented")

            rent_1 = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq_1.id, site_id=site_a.id, operator_id=op_a.id,
                check_out_date=date.today() - timedelta(days=5), expected_return_date=date.today() + timedelta(days=10),
                status="active"
            )
            rent_3 = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq_3.id, site_id=site_a.id, operator_id=op_a.id,
                check_out_date=date.today() - timedelta(days=25), expected_return_date=date.today() - timedelta(days=5),
                status="overdue"
            )

            db.add_all([site_a, op_a, eq_1, eq_2, eq_3, rent_1, rent_3])
            await db.flush()

            # Add telemetry logs (8 engine hours, 2 idle hours total = 80.0% utilization)
            db.add(UsageLog(
                id=uuid4(), tenant_id=tenant.id, rental_id=rent_1.id, equipment_id=eq_1.id, site_id=site_a.id, operator_id=op_a.id,
                log_date=date.today() - timedelta(days=1), engine_hours=8.0, idle_hours=2.0, fuel_litres=100.0
            ))

            await db.commit()
            return {"headers": headers, "site_id": str(site_a.id)}

    async def test_dashboard_summary_endpoint(self, client, dashboard_setup):
        setup = dashboard_setup
        resp = await client.get("/dashboard/summary", headers=setup["headers"])
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # 1. Check fleet status overview
        overview = data["fleet_overview"]
        assert overview["total_equipment"] == 3
        assert overview["status_counts"]["rented"] == 1
        assert overview["status_counts"]["available"] == 1
        assert overview["status_counts"]["overdue"] == 1
        assert overview["utilization_percentage"] == 80.0

        # 2. Check telemetry totals
        telem = data["telemetry_30d"]
        assert telem["total_engine_hours"] == 8.0
        assert telem["total_idle_hours"] == 2.0
        assert telem["total_fuel_litres"] == 100.0
        assert telem["wasted_idle_percentage"] == 20.0

        # 3. Check site breakdown
        sites = data["site_breakdown"]
        assert len(sites) >= 1
        site_a = [s for s in sites if s["name"] == "Apex Quarry"][0]
        assert site_a["active_equipment_count"] == 2

        # 4. Overdue count must be stable across repeated scans (regression:
        # rentals used to vanish from the report after the first status flip)
        resp2 = await client.get("/dashboard/summary", headers=setup["headers"])
        assert resp2.status_code == 200
        overview2 = resp2.json()["fleet_overview"]
        assert overview2["status_counts"]["overdue"] == 1
        assert overview2["status_counts"]["rented"] == 1

    async def test_dashboard_live_assets_endpoint(self, client, dashboard_setup):
        setup = dashboard_setup
        resp = await client.get("/dashboard/live-assets", headers=setup["headers"])
        assert resp.status_code == 200, resp.text
        assets = resp.json()
        assert len(assets) == 3

        # Verify deployment context & embedded risk health score
        by_code = {a["equipment_code"]: a for a in assets}
        ex = by_code["DASH-EX-1"]
        assert ex["current_deployment"]["site_name"] == "Apex Quarry"
        assert ex["current_deployment"]["operator_name"] == "Operator A"
        assert "health_and_risk" in ex

    async def test_live_assets_filtering(self, client, dashboard_setup):
        setup = dashboard_setup
        # Filter by available status
        resp = await client.get("/dashboard/live-assets?status=available", headers=setup["headers"])
        assert resp.status_code == 200
        assets = resp.json()
        assert len(assets) == 1
        assert assets[0]["equipment_code"] == "DASH-CR-2"

        # Filter by deployed site
        resp_site = await client.get(f"/dashboard/live-assets?site_id={setup['site_id']}", headers=setup["headers"])
        assert resp_site.status_code == 200
        site_assets = resp_site.json()
        assert len(site_assets) == 2  # DASH-EX-1 and DASH-BD-3 are deployed at site_a

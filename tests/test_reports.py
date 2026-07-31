"""Summary reports + remote immobilization (kill-switch)."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.equipment import Equipment
from models.operator import Operator
from models.rental import Rental
from models.site import Site
from models.tenant import Tenant
from models.usage_log import UsageLog


class TestReports:
    @pytest.fixture
    async def setup(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "RepCo", "tenant_slug": "repco",
            "email": "ops@repco.com", "password": "reports123",
        })
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "repco"))).scalar_one()
            site = Site(id=uuid4(), tenant_id=tenant.id, site_code="S-REP",
                        name="Report Site", location="Chennai")
            op = Operator(id=uuid4(), tenant_id=tenant.id, operator_code="OP-REP", name="Rep Op")
            eq = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="REP-EX-1",
                           equipment_type="Excavator", status="rented")
            rental = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq.id,
                site_id=site.id, operator_id=op.id,
                check_out_date=date.today() - timedelta(days=10),
                expected_return_date=date.today() + timedelta(days=10),
                status="active",
            )
            db.add_all([site, op, eq, rental])
            await db.flush()
            # 5 days: 8 engine + 2 idle = 80% utilization, 100 L/day
            for i in range(5):
                db.add(UsageLog(
                    id=uuid4(), tenant_id=tenant.id, rental_id=rental.id, equipment_id=eq.id,
                    site_id=site.id, operator_id=op.id,
                    log_date=date.today() - timedelta(days=i + 1),
                    engine_hours=8.0, idle_hours=2.0, fuel_litres=100.0,
                ))
            await db.commit()
            return {"headers": headers, "eq_id": str(eq.id)}

    async def test_summary_report_totals(self, client, setup):
        resp = await client.get("/reports/summary?window_days=30", headers=setup["headers"])
        assert resp.status_code == 200, resp.text
        data = resp.json()

        totals = data["usage_totals"]
        assert totals["engine_hours"] == 40.0
        assert totals["idle_hours"] == 10.0
        assert totals["total_rented_hours"] == 50.0
        assert totals["fuel_litres"] == 500.0
        assert totals["utilization_pct"] == 80.0
        assert totals["downtime_idle_ratio_pct"] == 20.0
        assert totals["machine_days_logged"] == 5

        site = [s for s in data["per_site"] if s["site_code"] == "S-REP"][0]
        assert site["engine_hours"] == 40.0
        assert site["utilization_pct"] == 80.0

        by_type = [t for t in data["per_equipment_type"] if t["equipment_type"] == "Excavator"][0]
        assert by_type["utilization_pct"] == 80.0

        rentals = data["rentals"]
        assert rentals["currently_open"] == 1
        assert rentals["currently_overdue"] == 0
        assert rentals["started_in_window"] == 1

    async def test_summary_window_filtering(self, client, setup):
        resp = await client.get("/reports/summary?window_days=1", headers=setup["headers"])
        assert resp.status_code == 200
        # only yesterday's log falls inside a 1-day window
        assert resp.json()["usage_totals"]["machine_days_logged"] == 1


class TestKillSwitch:
    @pytest.fixture
    async def setup(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "KillCo", "tenant_slug": "killco",
            "email": "dealer@killco.com", "password": "killswitch123",
        })
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "killco"))).scalar_one()
            eq = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="KILL-BD-1",
                           equipment_type="Bulldozer", status="available")
            db.add(eq)
            await db.commit()
            return {"headers": headers, "eq_id": str(eq.id)}

    async def test_immobilize_blocks_checkout_and_release_restores(self, client, setup):
        headers = setup["headers"]
        payload = {"equipment_code": "KILL-BD-1",
                   "expected_return_date": str(date.today() + timedelta(days=7))}

        disabled = await client.post(f"/equipment/{setup['eq_id']}/immobilize", headers=headers)
        assert disabled.status_code == 200
        assert disabled.json()["disabled"] is True

        blocked = await client.post("/rentals/checkout", json=payload, headers=headers)
        assert blocked.status_code == 400
        assert "immobilized" in blocked.json()["detail"]

        # the dashboard marks it so the dealer can see why
        assets = (await client.get("/dashboard/live-assets", headers=headers)).json()
        assert [a for a in assets if a["equipment_code"] == "KILL-BD-1"][0]["disabled"] is True

        released = await client.post(f"/equipment/{setup['eq_id']}/release", headers=headers)
        assert released.status_code == 200
        assert released.json()["disabled"] is False

        ok = await client.post("/rentals/checkout", json=payload, headers=headers)
        assert ok.status_code == 201, ok.text

    async def test_equipment_list_and_404(self, client, setup):
        listed = (await client.get("/equipment", headers=setup["headers"])).json()
        assert [e["equipment_code"] for e in listed] == ["KILL-BD-1"]
        assert listed[0]["disabled"] is False

        resp = await client.post(f"/equipment/{uuid4()}/immobilize", headers=setup["headers"])
        assert resp.status_code == 404

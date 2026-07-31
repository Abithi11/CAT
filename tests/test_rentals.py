"""Tests for rentals endpoints (checkout, checkin, qrcode)."""

from datetime import date, timedelta
from uuid import uuid4
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from models.equipment import Equipment
from models.site import Site
from models.operator import Operator
from models.tenant import Tenant


class TestRentals:
    @pytest.fixture
    async def rental_setup(self, client, engine):
        # Register a tenant and user to get token
        reg = await client.post("/auth/register", json={
            "tenant_name": "RentalCo", "tenant_slug": "rentalco",
            "email": "manager@rentalco.com", "password": "secretpassword",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Add equipment, site, and operator directly to db
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            from sqlalchemy import select
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "rentalco"))).scalar_one()
            eq = Equipment(
                id=uuid4(), tenant_id=tenant.id,
                equipment_code="QR-EXC-01", equipment_type="Excavator", status="available",
            )
            site = Site(
                id=uuid4(), tenant_id=tenant.id,
                site_code="S-999", name="Test Project", location="Delhi",
            )
            op = Operator(
                id=uuid4(), tenant_id=tenant.id,
                operator_code="OP-999", name="Test Operator",
            )
            db.add_all([eq, site, op])
            await db.commit()

            return {
                "headers": headers,
                "eq_id": str(eq.id),
                "eq_code": eq.equipment_code,
                "site_id": str(site.id),
                "op_id": str(op.id),
            }

    async def test_qrcode_endpoint(self, client, rental_setup):
        setup = rental_setup
        resp = await client.get(f"/equipment/{setup['eq_id']}/qrcode", headers=setup["headers"])
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0  # PNG image binary

    async def test_checkout_and_checkin_flow(self, client, rental_setup):
        setup = rental_setup

        # 1. Checkout equipment
        checkout_payload = {
            "equipment_code": setup["eq_code"],
            "site_id": setup["site_id"],
            "operator_id": setup["op_id"],
            "expected_return_date": str(date.today() + timedelta(days=14)),
        }
        resp = await client.post("/rentals/checkout", json=checkout_payload, headers=setup["headers"])
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "active"
        assert data["site_id"] == setup["site_id"]
        assert data["operator_id"] == setup["op_id"]

        # 2. Checkout again should fail (equipment already rented)
        resp2 = await client.post("/rentals/checkout", json=checkout_payload, headers=setup["headers"])
        assert resp2.status_code == 400
        assert "is not available" in resp2.json()["detail"]

        # 3. Checkin equipment
        checkin_payload = {"equipment_code": setup["eq_code"]}
        resp3 = await client.post("/rentals/checkin", json=checkin_payload, headers=setup["headers"])
        assert resp3.status_code == 200, resp3.text
        data3 = resp3.json()
        assert data3["status"] == "returned"
        assert data3["actual_return_date"] == str(date.today())

        # 4. Checkin again should fail (no active rental)
        resp4 = await client.post("/rentals/checkin", json=checkin_payload, headers=setup["headers"])
        assert resp4.status_code == 400
        assert "No active rental" in resp4.json()["detail"]

    async def test_checkout_invalid_equipment(self, client, rental_setup):
        setup = rental_setup
        resp = await client.post("/rentals/checkout", json={
            "equipment_code": "NONEXISTENT",
            "expected_return_date": str(date.today() + timedelta(days=5)),
        }, headers=setup["headers"])
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

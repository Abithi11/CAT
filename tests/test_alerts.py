"""Alert pipeline: scan -> alerts table -> dedup -> acknowledge, plus smtplib delivery."""

from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.equipment import Equipment
from models.rental import Rental
from models.tenant import Tenant
from models.usage_log import UsageLog


class TestAlerts:
    @pytest.fixture
    async def setup(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "AlertCo", "tenant_slug": "alertco",
            "email": "ops@alertco.com", "password": "alerts123",
        })
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "alertco"))).scalar_one()
            eq = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="AL-EX-1",
                           equipment_type="Excavator", status="rented")
            rental = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq.id,
                check_out_date=date.today() - timedelta(days=20),
                expected_return_date=date.today() - timedelta(days=4),
                status="active",
            )
            db.add_all([eq, rental])
            await db.flush()
            for i in range(6):
                db.add(UsageLog(
                    id=uuid4(), tenant_id=tenant.id, rental_id=rental.id, equipment_id=eq.id,
                    log_date=date.today() - timedelta(days=i + 1),
                    engine_hours=0.5, idle_hours=11.0, fuel_litres=6.0,
                    site_id=None, operator_id=None,
                ))
            await db.commit()
            return {"headers": headers, "tenant_id": tenant.id, "factory": factory}

    async def test_scan_creates_overdue_and_anomaly_alerts(self, client, setup):
        resp = await client.post("/alerts/scan", headers=setup["headers"])
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["created"] >= 2
        types = {a["alert_type"] for a in data["alerts"]}
        assert "overdue" in types
        assert "anomaly" in types
        assert all(a["email_sent"] == "skipped" for a in data["alerts"])  # SMTP unset in tests

    async def test_rescan_does_not_duplicate_open_alerts(self, client, setup):
        first = await client.post("/alerts/scan", headers=setup["headers"])
        second = await client.post("/alerts/scan", headers=setup["headers"])
        assert first.json()["created"] >= 2
        assert second.json()["created"] == 0, "open alerts must not be duplicated"

        listed = (await client.get("/alerts", headers=setup["headers"])).json()
        assert len(listed) == first.json()["created"]

    async def test_acknowledge_alert(self, client, setup):
        await client.post("/alerts/scan", headers=setup["headers"])
        alerts = (await client.get("/alerts?status=open", headers=setup["headers"])).json()
        assert alerts

        ack = await client.post(f"/alerts/{alerts[0]['id']}/acknowledge", headers=setup["headers"])
        assert ack.status_code == 200
        assert ack.json()["status"] == "acknowledged"
        assert ack.json()["acknowledged_at"] is not None

        still_open = (await client.get("/alerts?status=open", headers=setup["headers"])).json()
        assert len(still_open) == len(alerts) - 1

    async def test_acknowledge_unknown_alert_404(self, client, setup):
        resp = await client.post(f"/alerts/{uuid4()}/acknowledge", headers=setup["headers"])
        assert resp.status_code == 404

    async def test_email_delivery_invoked_when_smtp_configured(self, client, setup):
        """smtplib path: with SMTP configured, the scan sends one digest email."""
        from models.config import settings

        with patch.object(settings, "smtp_host", "smtp.example.com"), \
             patch.object(settings, "alert_email_to", "dealer@example.com"), \
             patch.object(settings, "smtp_user", "bot@example.com"), \
             patch.object(settings, "smtp_password", "app-password"), \
             patch("services.alerts.smtplib.SMTP") as mock_smtp:
            resp = await client.post("/alerts/scan", headers=setup["headers"])

        assert resp.status_code == 200
        assert resp.json()["created"] >= 1
        assert all(a["email_sent"] == "sent" for a in resp.json()["alerts"])
        smtp_instance = mock_smtp.return_value.__enter__.return_value
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("bot@example.com", "app-password")
        smtp_instance.send_message.assert_called_once()

    async def test_email_failure_marks_alert_not_scan(self, client, setup):
        from models.config import settings

        with patch.object(settings, "smtp_host", "smtp.example.com"), \
             patch.object(settings, "alert_email_to", "dealer@example.com"), \
             patch("services.alerts.smtplib.SMTP", side_effect=OSError("connection refused")):
            resp = await client.post("/alerts/scan", headers=setup["headers"])

        assert resp.status_code == 200, "email failure must not break the scan"
        assert all(a["email_sent"] == "failed" for a in resp.json()["alerts"])

    async def test_scheduler_job_scans_every_tenant(self, client, setup):
        """The APScheduler entry point runs standalone, over all active tenants."""
        from services.alerts import scan_all_tenants
        from models.alert import Alert

        with patch("utils.database.AsyncSessionLocal", setup["factory"]):
            await scan_all_tenants()

        async with setup["factory"]() as db:
            rows = (await db.execute(
                select(Alert).where(Alert.tenant_id == setup["tenant_id"])
            )).scalars().all()
        assert len(rows) >= 2

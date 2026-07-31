"""Alert pipeline: scan -> alerts table (dashboard demo path) -> smtplib email.

run_alert_scan is called by the APScheduler job (scan_all_tenants) and by the
manual POST /alerts/scan endpoint. Alerts are deduplicated: while an alert for
the same subject is still open, rescans don't create a duplicate.
"""

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.alert import Alert
from models.config import settings
from models.tenant import Tenant
from services.analytics import calculate_fleet_anomalies, detect_overdue_rentals

logger = logging.getLogger(__name__)

CRITICAL_ANOMALY_SCORE = 60


def serialize_alert(a: Alert) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "alert_type": a.alert_type,
        "severity": a.severity,
        "equipment_id": str(a.equipment_id) if a.equipment_id else None,
        "rental_id": str(a.rental_id) if a.rental_id else None,
        "message": a.message,
        "details": a.details,
        "status": a.status,
        "email_sent": a.email_sent,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
    }


async def _open_alert_exists(
    db: AsyncSession, tenant_id: UUID, alert_type: str,
    *, rental_id: UUID | None = None, equipment_id: UUID | None = None,
) -> bool:
    stmt = select(Alert.id).where(
        Alert.tenant_id == tenant_id,
        Alert.alert_type == alert_type,
        Alert.status == "open",
    )
    if rental_id is not None:
        stmt = stmt.where(Alert.rental_id == rental_id)
    if equipment_id is not None:
        stmt = stmt.where(Alert.equipment_id == equipment_id)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def run_alert_scan(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    """One full scan: overdue + approaching deadlines + critical anomalies."""
    new_alerts: list[Alert] = []

    report = await detect_overdue_rentals(db, tenant_id)
    for item in report["overdue"]:
        rid = UUID(item["rental_id"])
        if await _open_alert_exists(db, tenant_id, "overdue", rental_id=rid):
            continue
        new_alerts.append(Alert(
            tenant_id=tenant_id, alert_type="overdue", severity="critical",
            rental_id=rid,
            message=f"{item['equipment_code']} ({item['equipment_type']}) is "
                    f"{item['days_overdue']} day(s) overdue — expected back {item['expected_return_date']}",
            details=item,
        ))

    for item in report["approaching_deadline"]:
        rid = UUID(item["rental_id"])
        if await _open_alert_exists(db, tenant_id, "approaching_deadline", rental_id=rid):
            continue
        new_alerts.append(Alert(
            tenant_id=tenant_id, alert_type="approaching_deadline", severity="warning",
            rental_id=rid,
            message=f"{item['equipment_code']} ({item['equipment_type']}) is due back in "
                    f"{item['days_remaining']} day(s) ({item['expected_return_date']})",
            details=item,
        ))

    anomalies = await calculate_fleet_anomalies(db, tenant_id, window_days=30)
    for a in anomalies:
        if a["anomaly_score"] < CRITICAL_ANOMALY_SCORE:
            continue
        eq_id = UUID(a["equipment_id"])
        if await _open_alert_exists(db, tenant_id, "anomaly", equipment_id=eq_id):
            continue
        new_alerts.append(Alert(
            tenant_id=tenant_id, alert_type="anomaly", severity="critical",
            equipment_id=eq_id,
            message=f"{a['equipment_code']} anomaly score {a['anomaly_score']}: {a['explanation']}",
            details={"anomaly_score": a["anomaly_score"], "metrics": a["metrics"],
                     "explanation": a["explanation"]},
        ))

    email_status = await _deliver_email(tenant_id, db, new_alerts) if new_alerts else "skipped"
    for a in new_alerts:
        a.email_sent = email_status
        db.add(a)
    await db.flush()

    logger.info("Alert scan tenant=%s: %d new alerts (email: %s)",
                tenant_id, len(new_alerts), email_status)
    return {"created": len(new_alerts), "alerts": [serialize_alert(a) for a in new_alerts]}


async def scan_all_tenants() -> None:
    """APScheduler entry point — scans every active tenant with its own session."""
    from utils.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            tenants = (await db.execute(
                select(Tenant).where(Tenant.is_active == True)  # noqa: E712
            )).scalars().all()
            for t in tenants:
                await run_alert_scan(db, t.id)
            await db.commit()
    except Exception:
        logger.exception("Scheduled alert scan failed")


# --- email delivery (smtplib) ---

async def _deliver_email(tenant_id: UUID, db: AsyncSession, alerts: list[Alert]) -> str:
    if not settings.smtp_host or not settings.alert_email_to:
        return "skipped"
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(tenant_id)
    try:
        await asyncio.to_thread(_send_smtp, tenant_name, alerts)
        return "sent"
    except Exception as e:
        logger.warning("Alert email delivery failed: %s", e)
        return "failed"


def _send_smtp(tenant_name: str, alerts: list[Alert]) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[CAT Rental Tracker] {len(alerts)} new alert(s) — {tenant_name}"
    msg["From"] = settings.alert_email_from or settings.smtp_user or "alerts@cat-tracker.local"
    msg["To"] = settings.alert_email_to
    lines = [f"New alerts for {tenant_name} "
             f"({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}):", ""]
    for a in alerts:
        lines.append(f"- [{a.severity.upper()}] {a.alert_type}: {a.message}")
    lines += ["", "Open the dashboard for details and actions."]
    msg.set_content("\n".join(lines))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

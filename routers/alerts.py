from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.alert import Alert
from models.user import User
from services.alerts import run_alert_scan, serialize_alert
from utils.database import get_db

alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])


@alerts_router.get("", status_code=200)
async def list_alerts(
    status_filter: str | None = Query(None, alias="status", description="open | acknowledged"),
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Alert).where(Alert.tenant_id == user.tenant_id)
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)
    return [serialize_alert(a) for a in (await db.execute(stmt)).scalars().all()]


@alerts_router.post("/scan", status_code=200)
async def trigger_alert_scan(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manual trigger of the same scan APScheduler runs on an interval."""
    result = await run_alert_scan(db, user.tenant_id)
    await db.commit()
    return result


@alerts_router.post("/{alert_id}/acknowledge", status_code=200)
async def acknowledge_alert(
    alert_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    alert = (await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    return serialize_alert(alert)

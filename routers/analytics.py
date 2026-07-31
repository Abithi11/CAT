from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.user import User
from services.analytics import detect_overdue_rentals, calculate_fleet_anomalies
from utils.database import get_db

analytics_router = APIRouter(tags=["analytics"])


@analytics_router.post("/rentals/detect-overdue", status_code=200)
async def trigger_overdue_detection(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    """Scan active rentals for overdue returns and approaching return dates."""
    report = await detect_overdue_rentals(db, user.tenant_id)
    await db.commit()
    return report


@analytics_router.get("/analytics/anomalies", status_code=200)
async def get_fleet_anomalies(
    window_days: int = 30,
    min_score: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve vectorized NumPy anomaly scores (0-100) for all fleet assets."""
    anomalies = await calculate_fleet_anomalies(db, user.tenant_id, window_days=window_days)
    if min_score > 0:
        anomalies = [a for a in anomalies if a["anomaly_score"] >= min_score]
    return anomalies

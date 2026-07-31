from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.user import User
from services.reports import get_summary_report
from utils.database import get_db

reports_router = APIRouter(prefix="/reports", tags=["reports"])


@reports_router.get("/summary", status_code=200)
async def summary_report(
    window_days: int = Query(30, ge=1, le=730),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Total rented hours, per-site utilization, downtime and idle ratios."""
    return await get_summary_report(db, user.tenant_id, window_days=window_days)

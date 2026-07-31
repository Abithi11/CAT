from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.user import User
from services.dashboard import get_dashboard_summary, get_live_assets
from utils.database import get_db

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard_router.get("/summary", status_code=200)
async def dashboard_summary_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve real-time asset counts, telemetry KPIs, site breakdowns, and alert summaries."""
    summary = await get_dashboard_summary(db, user.tenant_id)
    await db.commit()  # commit any overdue status flips triggered during report generation
    return summary


@dashboard_router.get("/live-assets", status_code=200)
async def dashboard_live_assets_endpoint(
    status: str | None = Query(None, description="Filter by asset status (available, rented, overdue)"),
    site_id: UUID | None = Query(None, description="Filter by deployed site UUID"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve live status, current deployment context, and risk anomaly score for each machine."""
    assets = await get_live_assets(db, user.tenant_id, status_filter=status, site_id=site_id)
    await db.commit()
    return assets

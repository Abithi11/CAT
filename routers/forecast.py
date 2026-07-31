from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.user import User
from services.forecasting import forecast_demand, rebalancing_recommendations
from utils.database import get_db

forecast_router = APIRouter(prefix="/forecast", tags=["forecast"])


@forecast_router.get("", status_code=200)
async def get_forecast(
    horizon_months: int = Query(3, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Probabilistic rental demand per equipment-type x site x month (NGBoost).

    Trains on the tenant's history at call time — first call after a big seed
    takes a few seconds.
    """
    return await forecast_demand(db, user.tenant_id, horizon_months=horizon_months)


@forecast_router.get("/rebalancing", status_code=200)
async def get_rebalancing(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Greedy assignment of forecasted demand to idle machines, with ₹ saved."""
    return await rebalancing_recommendations(db, user.tenant_id)

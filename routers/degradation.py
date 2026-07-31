from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.equipment import Equipment
from models.user import User
from services.degradation import fleet_degradation, trace_equipment, validate_against_ground_truth
from utils.database import get_db

degradation_router = APIRouter(tags=["degradation"])


@degradation_router.get("/equipment/{equipment_id}/degradation", status_code=200)
async def equipment_degradation(
    equipment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Health timeline + detected onset + custody attribution for one machine."""
    eq = (await db.execute(
        select(Equipment).where(Equipment.id == equipment_id, Equipment.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return await trace_equipment(db, user.tenant_id, eq, include_timeline=True)


@degradation_router.get("/degradation/fleet", status_code=200)
async def fleet_degradation_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Degradation status of every machine, worst first (no timelines)."""
    return await fleet_degradation(db, user.tenant_id)


@degradation_router.post("/degradation/validate", status_code=200)
async def validate_degradation(
    tolerance_days: int = Query(30, ge=1, le=120),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Score the tracer against planted ground truth — produces the pitch-slide
    accuracy number."""
    return await validate_against_ground_truth(db, user.tenant_id, tolerance_days=tolerance_days)

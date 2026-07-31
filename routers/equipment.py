from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.equipment import Equipment
from models.user import User
from utils.database import get_db

equipment_router = APIRouter(prefix="/equipment", tags=["equipment"])


def _serialize(eq: Equipment) -> dict[str, Any]:
    return {
        "id": str(eq.id),
        "equipment_code": eq.equipment_code,
        "equipment_type": eq.equipment_type,
        "status": eq.status,
        "disabled": bool(eq.disabled),
    }


@equipment_router.get("", status_code=200)
async def list_equipment(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(Equipment).where(Equipment.tenant_id == user.tenant_id)
        .order_by(Equipment.equipment_code)
    )).scalars().all()
    return [_serialize(eq) for eq in rows]


async def _set_kill_switch(equipment_id: UUID, disabled: bool, user: User,
                           db: AsyncSession) -> dict[str, Any]:
    eq = (await db.execute(
        select(Equipment).where(Equipment.id == equipment_id,
                                Equipment.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")
    eq.disabled = disabled
    await db.commit()
    return _serialize(eq)


@equipment_router.post("/{equipment_id}/immobilize", status_code=200)
async def immobilize(
    equipment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Simulated remote kill-switch: machine is blocked from checkout and
    flagged on the dashboard. No hardware anywhere."""
    return await _set_kill_switch(equipment_id, True, user, db)


@equipment_router.post("/{equipment_id}/release", status_code=200)
async def release(
    equipment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _set_kill_switch(equipment_id, False, user, db)

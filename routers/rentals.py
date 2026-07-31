import io
from datetime import date
from uuid import UUID

import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from models.equipment import Equipment
from models.rental import Rental
from models.user import User
from services import checkout_equipment, checkin_equipment, log_usage
from utils.database import get_db

rentals_router = APIRouter(tags=["rentals"])


# --- Schemas ---

class CheckoutRequest(BaseModel):
    equipment_code: str
    site_id: UUID | None = None
    operator_id: UUID | None = None
    expected_return_date: date


class CheckinRequest(BaseModel):
    equipment_code: str


class RentalResponse(BaseModel):
    id: UUID
    equipment_id: UUID
    site_id: UUID | None
    operator_id: UUID | None
    check_out_date: date
    expected_return_date: date
    actual_return_date: date | None
    status: str

    model_config = {"from_attributes": True}


class UsageLogRequest(BaseModel):
    equipment_code: str
    log_date: date | None = None
    engine_hours: float = Field(0.0, ge=0.0, le=24.0)
    idle_hours: float = Field(0.0, ge=0.0, le=24.0)
    fuel_litres: float = Field(0.0, ge=0.0)
    site_id: UUID | None = None
    operator_id: UUID | None = None

    @model_validator(mode="after")
    def check_total_hours(self):
        if self.engine_hours + self.idle_hours > 24.0:
            raise ValueError("engine_hours + idle_hours cannot exceed 24 per day")
        return self


class UsageLogResponse(BaseModel):
    id: UUID
    rental_id: UUID
    equipment_id: UUID
    site_id: UUID | None
    operator_id: UUID | None
    log_date: date
    engine_hours: float
    idle_hours: float
    fuel_litres: float

    model_config = {"from_attributes": True}


# --- Endpoints ---

@rentals_router.post("/rentals/checkout", response_model=RentalResponse, status_code=201)
async def checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rental = await checkout_equipment(
            db, user.tenant_id, body.equipment_code,
            site_id=body.site_id, operator_id=body.operator_id,
            expected_return_date=body.expected_return_date,
        )
        await db.commit()
        return rental
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@rentals_router.post("/rentals/checkin", response_model=RentalResponse)
async def checkin(
    body: CheckinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rental = await checkin_equipment(db, user.tenant_id, body.equipment_code)
        await db.commit()
        return rental
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@rentals_router.post("/usage", response_model=UsageLogResponse, status_code=201)
async def post_usage(
    body: UsageLogRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record one day of telemetry against the machine's open rental.

    The machine is identified by equipment_code (the value its QR code encodes).
    site/operator default to the rental's own when not supplied.
    """
    eq = (await db.execute(
        select(Equipment).where(Equipment.tenant_id == user.tenant_id, Equipment.equipment_code == body.equipment_code)
    )).scalar_one_or_none()
    if not eq:
        raise HTTPException(status_code=404, detail=f"Equipment '{body.equipment_code}' not found")

    rental = (await db.execute(
        select(Rental).where(Rental.equipment_id == eq.id, Rental.actual_return_date.is_(None))
    )).scalar_one_or_none()
    if not rental:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"No open rental for '{body.equipment_code}'")

    entry = await log_usage(
        db, user.tenant_id, rental.id, eq.id,
        body.log_date or date.today(),
        body.engine_hours, body.idle_hours, body.fuel_litres,
        site_id=body.site_id if body.site_id is not None else rental.site_id,
        operator_id=body.operator_id if body.operator_id is not None else rental.operator_id,
    )
    await db.commit()
    return entry


@rentals_router.get("/equipment/{equipment_id}/qrcode")
async def get_qrcode(
    equipment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a QR code PNG encoding the equipment_code."""
    eq = (await db.execute(
        select(Equipment).where(Equipment.id == equipment_id, Equipment.tenant_id == user.tenant_id)
    )).scalar_one_or_none()

    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    img = qrcode.make(eq.equipment_code)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Content-Disposition": f"inline; filename={eq.equipment_code}.png"})

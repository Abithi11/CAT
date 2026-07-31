"""Rental business logic — checkout, checkin, usage logging.

Both the API endpoints and the synthetic generator call these functions,
ensuring all data flows through the same validation path.
"""

import logging
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.rental import Rental
from models.usage_log import UsageLog

logger = logging.getLogger(__name__)


async def checkout_equipment(
    db: AsyncSession,
    tenant_id: UUID,
    equipment_code: str,
    *,
    site_id: UUID | None = None,
    operator_id: UUID | None = None,
    expected_return_date: date,
    check_out_date: date | None = None,
) -> Rental:
    """Create a rental and mark equipment as rented.

    Raises ValueError if equipment not found or not available.
    """
    check_out_date = check_out_date or date.today()

    eq = (await db.execute(
        select(Equipment).where(Equipment.tenant_id == tenant_id, Equipment.equipment_code == equipment_code)
    )).scalar_one_or_none()

    if not eq:
        raise ValueError(f"Equipment '{equipment_code}' not found")
    if eq.status != "available":
        raise ValueError(f"Equipment '{equipment_code}' is not available (status={eq.status})")

    eq.status = "rented"

    rental = Rental(
        id=uuid4(), tenant_id=tenant_id, equipment_id=eq.id,
        site_id=site_id, operator_id=operator_id,
        check_out_date=check_out_date, expected_return_date=expected_return_date,
        status="active",
    )
    db.add(rental)
    await db.flush()
    logger.info("Checked out %s → rental %s (site=%s, op=%s)", equipment_code, rental.id, site_id, operator_id)
    return rental


async def checkin_equipment(
    db: AsyncSession,
    tenant_id: UUID,
    equipment_code: str,
    *,
    actual_return_date: date | None = None,
) -> Rental:
    """Close the active rental for this equipment and mark it available.

    Raises ValueError if no active rental found.
    """
    actual_return_date = actual_return_date or date.today()

    eq = (await db.execute(
        select(Equipment).where(Equipment.tenant_id == tenant_id, Equipment.equipment_code == equipment_code)
    )).scalar_one_or_none()

    if not eq:
        raise ValueError(f"Equipment '{equipment_code}' not found")

    rental = (await db.execute(
        select(Rental).where(Rental.equipment_id == eq.id, Rental.status == "active")
    )).scalar_one_or_none()

    if not rental:
        raise ValueError(f"No active rental for '{equipment_code}'")

    rental.actual_return_date = actual_return_date
    rental.status = "overdue" if actual_return_date > rental.expected_return_date else "returned"
    eq.status = "available"

    await db.flush()
    logger.info("Checked in %s → rental %s (%s)", equipment_code, rental.id, rental.status)
    return rental


async def log_usage(
    db: AsyncSession,
    tenant_id: UUID,
    rental_id: UUID,
    equipment_id: UUID,
    log_date: date,
    engine_hours: float,
    idle_hours: float,
    fuel_litres: float,
    *,
    site_id: UUID | None = None,
    operator_id: UUID | None = None,
) -> UsageLog:
    """Record a single day's telemetry for a rental."""
    entry = UsageLog(
        id=uuid4(), tenant_id=tenant_id, rental_id=rental_id,
        equipment_id=equipment_id, site_id=site_id, operator_id=operator_id,
        log_date=log_date, engine_hours=engine_hours,
        idle_hours=idle_hours, fuel_litres=fuel_litres,
    )
    db.add(entry)
    return entry

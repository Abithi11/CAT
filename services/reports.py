"""Summary reports: total rented hours, per-site utilization, downtime, idle ratios."""

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.rental import Rental
from models.site import Site
from models.usage_log import UsageLog

EPS = 1e-6


def _util(engine_h: float, idle_h: float) -> float:
    return round(engine_h / (engine_h + idle_h + EPS) * 100, 1)


async def get_summary_report(db: AsyncSession, tenant_id: UUID, window_days: int = 30) -> dict[str, Any]:
    today = date.today()
    cutoff = today - timedelta(days=window_days)

    # Fleet-wide usage totals
    eng, idle, fuel, log_days = (await db.execute(
        select(
            func.coalesce(func.sum(UsageLog.engine_hours), 0.0),
            func.coalesce(func.sum(UsageLog.idle_hours), 0.0),
            func.coalesce(func.sum(UsageLog.fuel_litres), 0.0),
            func.count(UsageLog.id),
        ).where(UsageLog.tenant_id == tenant_id, UsageLog.log_date >= cutoff)
    )).one()
    eng, idle, fuel = float(eng), float(idle), float(fuel)

    # Per-site usage
    site_rows = (await db.execute(
        select(
            Site.site_code, Site.name, Site.location,
            func.coalesce(func.sum(UsageLog.engine_hours), 0.0),
            func.coalesce(func.sum(UsageLog.idle_hours), 0.0),
            func.coalesce(func.sum(UsageLog.fuel_litres), 0.0),
        )
        .outerjoin(UsageLog, (UsageLog.site_id == Site.id) & (UsageLog.log_date >= cutoff))
        .where(Site.tenant_id == tenant_id)
        .group_by(Site.id, Site.site_code, Site.name, Site.location)
    )).all()

    # Per-equipment-type usage
    type_rows = (await db.execute(
        select(
            Equipment.equipment_type,
            func.coalesce(func.sum(UsageLog.engine_hours), 0.0),
            func.coalesce(func.sum(UsageLog.idle_hours), 0.0),
        )
        .join(UsageLog, (UsageLog.equipment_id == Equipment.id) & (UsageLog.log_date >= cutoff))
        .where(Equipment.tenant_id == tenant_id)
        .group_by(Equipment.equipment_type)
    )).all()

    # Rental activity
    started = (await db.execute(
        select(func.count(Rental.id)).where(
            Rental.tenant_id == tenant_id, Rental.check_out_date >= cutoff)
    )).scalar_one()
    open_now = (await db.execute(
        select(func.count(Rental.id)).where(
            Rental.tenant_id == tenant_id, Rental.actual_return_date.is_(None))
    )).scalar_one()
    overdue_now = (await db.execute(
        select(func.count(Rental.id)).where(
            Rental.tenant_id == tenant_id, Rental.actual_return_date.is_(None),
            Rental.expected_return_date < today)
    )).scalar_one()
    completed = (await db.execute(
        select(Rental).where(
            Rental.tenant_id == tenant_id,
            Rental.actual_return_date.isnot(None),
            Rental.actual_return_date >= cutoff)
    )).scalars().all()
    durations = [(r.actual_return_date - r.check_out_date).days for r in completed]
    on_time = sum(1 for r in completed if r.actual_return_date <= r.expected_return_date)

    return {
        "window_days": window_days,
        "generated_at": today.isoformat(),
        "usage_totals": {
            "total_rented_hours": round(eng + idle, 1),
            "engine_hours": round(eng, 1),
            "idle_hours": round(idle, 1),
            "fuel_litres": round(fuel, 1),
            "utilization_pct": _util(eng, idle),
            "downtime_idle_ratio_pct": round(100 - _util(eng, idle), 1) if (eng + idle) > 0 else 0.0,
            "machine_days_logged": int(log_days),
        },
        "per_site": [
            {
                "site_code": code, "name": name, "location": loc,
                "engine_hours": round(float(e), 1), "idle_hours": round(float(i), 1),
                "fuel_litres": round(float(f), 1), "utilization_pct": _util(float(e), float(i)),
            }
            for code, name, loc, e, i, f in site_rows
        ],
        "per_equipment_type": [
            {
                "equipment_type": t,
                "engine_hours": round(float(e), 1), "idle_hours": round(float(i), 1),
                "utilization_pct": _util(float(e), float(i)),
            }
            for t, e, i in type_rows
        ],
        "rentals": {
            "started_in_window": int(started),
            "currently_open": int(open_now),
            "currently_overdue": int(overdue_now),
            "completed_in_window": len(completed),
            "avg_rental_duration_days": round(sum(durations) / len(durations), 1) if durations else 0.0,
            "on_time_return_pct": round(on_time / len(completed) * 100, 1) if completed else 100.0,
        },
    }

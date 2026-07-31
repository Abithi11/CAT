"""Live Asset Dashboard service layer.

Aggregates real-time asset counts, telemetry runtime/idle ratios, per-site deployment
statistics, and live anomaly/overdue risk feeds into consolidated summary reports.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.operator import Operator
from models.rental import Rental
from models.site import Site
from models.usage_log import UsageLog
from services.analytics import calculate_fleet_anomalies, detect_overdue_rentals


async def get_dashboard_summary(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    """Compile real-time KPI summary, asset counts, site breakdown, and active alerts."""
    # 1. Asset status count breakdown
    stat_query = (
        select(Equipment.status, func.count(Equipment.id))
        .where(Equipment.tenant_id == tenant_id)
        .group_by(Equipment.status)
    )
    res_stats = await db.execute(stat_query)
    status_counts = {"available": 0, "rented": 0, "overdue": 0, "maintenance": 0}
    for st, cnt in res_stats.all():
        status_counts[st.lower()] = cnt
    total_equipment = sum(status_counts.values())

    # 2. Telemetry totals (last 30 days)
    cutoff = date.today() - timedelta(days=30)
    telem_query = (
        select(
            func.coalesce(func.sum(UsageLog.engine_hours), 0.0),
            func.coalesce(func.sum(UsageLog.idle_hours), 0.0),
            func.coalesce(func.sum(UsageLog.fuel_litres), 0.0),
        )
        .where(UsageLog.tenant_id == tenant_id, UsageLog.log_date >= cutoff)
    )
    eng_tot, idle_tot, fuel_tot = (await db.execute(telem_query)).one()
    eng_tot, idle_tot, fuel_tot = float(eng_tot), float(idle_tot), float(fuel_tot)

    # Calculate utilization efficiency percentage using NumPy logic
    eps = 1e-6
    utilization_pct = round(float(eng_tot / (eng_tot + idle_tot + eps)) * 100, 1)

    # 3. Active site deployments
    site_query = (
        select(Site.id, Site.name, Site.location, func.count(Rental.id))
        .outerjoin(Rental, (Rental.site_id == Site.id) & (Rental.status.in_(["active", "overdue"])))
        .where(Site.tenant_id == tenant_id)
        .group_by(Site.id, Site.name, Site.location)
    )
    site_rows = (await db.execute(site_query)).all()
    site_breakdown = [
        {"site_id": str(r[0]), "name": r[1], "location": r[2], "active_equipment_count": r[3]}
        for r in site_rows
    ]

    # 4. Integrate high-priority analytics risks
    anomalies = await calculate_fleet_anomalies(db, tenant_id, window_days=30)
    critical_anomalies = [a for a in anomalies if a["anomaly_score"] >= 60]
    overdue_report = await detect_overdue_rentals(db, tenant_id)

    return {
        "fleet_overview": {
            "total_equipment": total_equipment,
            "status_counts": status_counts,
            "utilization_percentage": utilization_pct,
        },
        "telemetry_30d": {
            "total_engine_hours": round(eng_tot, 1),
            "total_idle_hours": round(idle_tot, 1),
            "total_fuel_litres": round(fuel_tot, 1),
            "wasted_idle_percentage": round(100.0 - utilization_pct, 1) if (eng_tot + idle_tot) > 0 else 0.0,
        },
        "site_breakdown": site_breakdown,
        "alerts_summary": {
            "critical_anomalies_count": len(critical_anomalies),
            "overdue_rentals_count": len(overdue_report["overdue"]),
            "approaching_deadline_count": len(overdue_report["approaching_deadline"]),
            "critical_anomalies": critical_anomalies[:5],  # top 5 highest severity items
            "overdue_rentals": overdue_report["overdue"][:5],
        },
    }


async def get_live_assets(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    status_filter: str | None = None,
    site_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Fetch live feed of all fleet machines with current deployment context & anomaly health scores."""
    # Build query to pull equipment with active rental, site, and operator names
    query = (
        select(
            Equipment,
            Rental.id, Rental.expected_return_date, Rental.check_out_date,
            Site.id, Site.name,
            Operator.id, Operator.name,
        )
        .outerjoin(Rental, (Rental.equipment_id == Equipment.id) & (Rental.status.in_(["active", "overdue"])))
        .outerjoin(Site, Rental.site_id == Site.id)
        .outerjoin(Operator, Rental.operator_id == Operator.id)
        .where(Equipment.tenant_id == tenant_id)
    )

    if status_filter:
        query = query.where(func.lower(Equipment.status) == status_filter.lower())
    if site_id:
        query = query.where(Rental.site_id == site_id)

    rows = (await db.execute(query)).all()

    # Pre-compute anomaly health scores across fleet
    anomalies = await calculate_fleet_anomalies(db, tenant_id, window_days=30)
    score_map = {a["equipment_id"]: (a["anomaly_score"], a["severity"], a["explanation"]) for a in anomalies}

    live_feed = []
    for eq, rent_id, exp_date, out_date, s_id, s_name, op_id, op_name in rows:
        score, severity, explanation = score_map.get(str(eq.id), (0, "Normal", "Healthy"))
        live_feed.append({
            "equipment_id": str(eq.id),
            "equipment_code": eq.equipment_code,
            "equipment_type": eq.equipment_type,
            "status": eq.status,
            "current_deployment": {
                "rental_id": str(rent_id) if rent_id else None,
                "site_id": str(s_id) if s_id else None,
                "site_name": s_name if s_name else "Unassigned / Depot",
                "operator_id": str(op_id) if op_id else None,
                "operator_name": op_name if op_name else "None",
                "check_out_date": str(out_date) if out_date else None,
                "expected_return_date": str(exp_date) if exp_date else None,
            },
            "health_and_risk": {
                "anomaly_score": score,
                "severity": severity,
                "diagnostic_note": explanation,
            },
        })

    return live_feed

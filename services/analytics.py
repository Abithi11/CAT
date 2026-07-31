"""Analytics & Anomaly Detection service layer.

Implements vectorized NumPy anomaly scoring (0-100 scale) to detect operational
misuse, excessive idling, ghost rentals (NULL site/operator), and fuel efficiency drift.
Also implements the overdue rental detection engine.
"""

import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.rental import Rental
from models.usage_log import UsageLog

logger = logging.getLogger(__name__)


async def detect_overdue_rentals(db: AsyncSession, tenant_id: UUID) -> dict[str, list[dict[str, Any]]]:
    """Scan all open rentals (not yet returned) for overdue items and approaching deadlines.

    Idempotent: already-flagged overdue rentals are re-reported on every scan
    until the equipment is checked in.
    """
    today = date.today()
    result = await db.execute(
        select(Rental, Equipment.equipment_code, Equipment.equipment_type)
        .join(Equipment, Rental.equipment_id == Equipment.id)
        .where(Rental.tenant_id == tenant_id, Rental.actual_return_date.is_(None))
    )
    rows = result.all()

    overdue_list = []
    approaching_list = []

    for rental, eq_code, eq_type in rows:
        diff = (rental.expected_return_date - today).days
        if diff < 0:
            rental.status = "overdue"
            overdue_list.append({
                "rental_id": str(rental.id),
                "equipment_code": eq_code,
                "equipment_type": eq_type,
                "expected_return_date": str(rental.expected_return_date),
                "days_overdue": abs(diff),
                "status": "overdue",
            })
        elif 0 <= diff <= 2:
            approaching_list.append({
                "rental_id": str(rental.id),
                "equipment_code": eq_code,
                "equipment_type": eq_type,
                "expected_return_date": str(rental.expected_return_date),
                "days_remaining": diff,
                "status": "approaching_deadline",
            })

    await db.flush()
    logger.info("Overdue scan: %d overdue, %d approaching for tenant %s",
                len(overdue_list), len(approaching_list), tenant_id)
    return {"overdue": overdue_list, "approaching_deadline": approaching_list}


async def calculate_fleet_anomalies(
    db: AsyncSession, tenant_id: UUID, window_days: int = 30
) -> list[dict[str, Any]]:
    """Calculate vectorized NumPy anomaly scores (0-100) for tenant's equipment fleet."""
    cutoff_date = date.today() - timedelta(days=window_days)

    # 1. Fetch all equipment
    eq_res = await db.execute(select(Equipment).where(Equipment.tenant_id == tenant_id))
    equipment_list = eq_res.scalars().all()

    # 2. Fetch usage logs within window
    log_res = await db.execute(
        select(UsageLog).where(UsageLog.tenant_id == tenant_id, UsageLog.log_date >= cutoff_date)
    )
    logs = log_res.scalars().all()

    # Group logs by equipment_id and compute fleet fuel rate baselines per equipment_type
    logs_by_eq: dict[UUID, list[UsageLog]] = {e.id: [] for e in equipment_list}
    rates_by_type: dict[str, list[float]] = {}
    eq_type_map = {e.id: e.equipment_type for e in equipment_list}

    for lg in logs:
        if lg.equipment_id in logs_by_eq:
            logs_by_eq[lg.equipment_id].append(lg)
            eq_type = eq_type_map.get(lg.equipment_id, "Unknown")
            tot_h = lg.engine_hours + lg.idle_hours
            if tot_h > 0:
                rates_by_type.setdefault(eq_type, []).append(lg.fuel_litres / tot_h)

    # Compute fleet baseline mean and std for fuel consumption
    baselines: dict[str, tuple[float, float]] = {}
    for etype, rates in rates_by_type.items():
        arr = np.array(rates, dtype=np.float64)
        baselines[etype] = (float(np.mean(arr)), float(np.std(arr)) if len(arr) > 1 else 1.0)

    results = []
    eps = 1e-6

    # 3. Vectorized NumPy Scoring per equipment
    for eq in equipment_list:
        eq_logs = logs_by_eq.get(eq.id, [])
        if not eq_logs:
            results.append({
                "equipment_id": str(eq.id),
                "equipment_code": eq.equipment_code,
                "equipment_type": eq.equipment_type,
                "status": eq.status,
                "anomaly_score": 0,
                "severity": "Normal",
                "metrics": {"idle_ratio": 0.0, "ghost_ratio": 0.0, "fuel_z_score": 0.0, "logs_analyzed": 0},
                "explanation": "No telemetry logs within evaluation window.",
            })
            continue

        # Extract NumPy vectors
        engine_arr = np.array([lg.engine_hours for lg in eq_logs], dtype=np.float64)
        idle_arr = np.array([lg.idle_hours for lg in eq_logs], dtype=np.float64)
        fuel_arr = np.array([lg.fuel_litres for lg in eq_logs], dtype=np.float64)
        ghost_arr = np.array([1.0 if (lg.site_id is None or lg.operator_id is None) else 0.0 for lg in eq_logs], dtype=np.float64)

        total_arr = engine_arr + idle_arr
        idle_ratios = idle_arr / (total_arr + eps)
        s_idle = float(np.mean(idle_ratios))
        s_ghost = float(np.mean(ghost_arr))

        # Fuel Z-Score calculation against class baseline
        mu, sigma = baselines.get(eq.equipment_type, (10.0, 2.0))
        rates = fuel_arr / (total_arr + eps)
        z_scores = np.maximum(0.0, (rates - mu) / (sigma + eps))
        s_fuel = min(1.0, float(np.mean(z_scores)) / 3.0)

        # Composite score (0 to 100)
        raw_score = 45.0 * s_idle + 40.0 * s_ghost + 15.0 * s_fuel
        score = min(100, int(np.round(raw_score)))

        # Severity & explanation formulation
        if score >= 60:
            severity = "Critical Anomaly"
        elif score >= 35:
            severity = "Warning"
        else:
            severity = "Normal"

        reasons = []
        if s_idle > 0.50:
            reasons.append(f"High underutilization: machine idled {s_idle*100:.1f}% of total running time")
        if s_ghost > 0.10:
            reasons.append(f"Untraceable operations: {s_ghost*100:.1f}% of usage logged with NULL site or operator")
        if s_fuel > 0.33:
            reasons.append(f"Anomalous fuel efficiency drift (Z-score > 1.0) compared to {eq.equipment_type} baseline")

        explanation = "; ".join(reasons) if reasons else "Equipment operating within normal efficiency & utilization limits."

        results.append({
            "equipment_id": str(eq.id),
            "equipment_code": eq.equipment_code,
            "equipment_type": eq.equipment_type,
            "status": eq.status,
            "anomaly_score": score,
            "severity": severity,
            "metrics": {
                "idle_ratio": round(s_idle, 3),
                "ghost_ratio": round(s_ghost, 3),
                "fuel_z_score": round(float(np.mean(z_scores)), 3),
                "logs_analyzed": len(eq_logs),
            },
            "explanation": explanation,
        })

    # Sort results by highest anomaly score first
    results.sort(key=lambda x: x["anomaly_score"], reverse=True)
    return results

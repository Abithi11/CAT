"""Probabilistic demand forecasting (NGBoost) + rebalancing recommendations.

Target: rentals per equipment-type x site x month, forecast as probability
distributions (Normal), never point estimates. With too little history the
model falls back to a seasonal baseline so the endpoint always answers.
"""

import logging
from datetime import date
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
from scipy.stats import norm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.rental import Rental
from models.site import Site

logger = logging.getLogger(__name__)

MIN_ROWS_FOR_NGBOOST = 24

# ₹/month idle-holding cost per machine class (fleet-manager heuristics for the pitch)
IDLE_COST_PER_MONTH = {
    "Excavator": 48_000, "Crane": 65_000, "Bulldozer": 55_000,
    "Grader": 40_000, "Loader": 45_000, "Compactor": 30_000,
}


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


async def _history_frame(db: AsyncSession, tenant_id: UUID) -> tuple[pd.DataFrame, dict]:
    """Monthly rental counts per (equipment_type, site), zero-filled across the
    observed date range so quiet months count as real zeros."""
    rows = (await db.execute(
        select(Rental.check_out_date, Equipment.equipment_type, Rental.site_id)
        .join(Equipment, Rental.equipment_id == Equipment.id)
        .where(Rental.tenant_id == tenant_id, Rental.site_id.isnot(None))
    )).all()
    sites = {
        s.id: {"site_code": s.site_code, "site_name": s.name}
        for s in (await db.execute(
            select(Site).where(Site.tenant_id == tenant_id)
        )).scalars().all()
    }
    if not rows:
        return pd.DataFrame(), sites

    df = pd.DataFrame(
        [(_month_start(d), t, str(sid)) for d, t, sid in rows],
        columns=["month", "equipment_type", "site_id"],
    )
    counts = df.groupby(["month", "equipment_type", "site_id"]).size().rename("rentals").reset_index()

    months = sorted(counts["month"].unique())
    all_months = []
    m = months[0]
    while m <= months[-1]:
        all_months.append(m)
        m = _add_months(m, 1)
    combos = counts[["equipment_type", "site_id"]].drop_duplicates()
    grid = combos.merge(pd.DataFrame({"month": all_months}), how="cross")
    full = grid.merge(counts, on=["month", "equipment_type", "site_id"], how="left").fillna({"rentals": 0})
    full["rentals"] = full["rentals"].astype(float)
    t0 = all_months[0]
    full["t"] = full["month"].map(lambda d: (d.year - t0.year) * 12 + (d.month - t0.month))
    return full, sites


def _feature_matrix(df: pd.DataFrame, columns: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    feats = pd.DataFrame({
        "t": df["t"].astype(float),
        "month_sin": np.sin(2 * np.pi * df["month"].map(lambda d: d.month) / 12),
        "month_cos": np.cos(2 * np.pi * df["month"].map(lambda d: d.month) / 12),
    })
    dummies = pd.get_dummies(df[["equipment_type", "site_id"]], dtype=float)
    feats = pd.concat([feats.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)
    if columns is not None:
        feats = feats.reindex(columns=columns, fill_value=0.0)
    return feats.to_numpy(dtype=float), list(feats.columns)


def _row_payload(eq_type: str, site_id: str, sites: dict, month: date,
                 loc: float, scale: float) -> dict[str, Any]:
    loc = max(0.0, float(loc))
    scale = max(0.35, float(scale))  # floor keeps probabilities honest on tiny data
    site_meta = sites.get(UUID(site_id), {"site_code": "?", "site_name": "Unknown"})
    return {
        "equipment_type": eq_type,
        "site_id": site_id,
        "site_code": site_meta["site_code"],
        "site_name": site_meta["site_name"],
        "month": month.strftime("%Y-%m"),
        "expected_rentals": round(loc, 2),
        "p10": round(max(0.0, loc - 1.2816 * scale), 2),
        "p90": round(loc + 1.2816 * scale, 2),
        "prob_at_least": {
            str(k): round(float(1 - norm.cdf(k - 0.5, loc=loc, scale=scale)), 3)
            for k in (1, 2, 3)
        },
    }


async def forecast_demand(db: AsyncSession, tenant_id: UUID, horizon_months: int = 3) -> dict[str, Any]:
    history, sites = await _history_frame(db, tenant_id)
    if history.empty:
        return {"model": "none", "horizon_months": horizon_months, "rows": [],
                "note": "No rental history with assigned sites yet — seed data first."}

    next_month = _add_months(_month_start(date.today()), 1)
    combos = history[["equipment_type", "site_id"]].drop_duplicates()
    future = combos.merge(
        pd.DataFrame({"month": [_add_months(next_month, i) for i in range(horizon_months)]}),
        how="cross",
    )
    t0_offset = int(history["t"].max()) + 1
    first_future = future["month"].min()
    future["t"] = future["month"].map(
        lambda d: t0_offset + (d.year - first_future.year) * 12 + (d.month - first_future.month))

    model_name = "ngboost"
    try:
        if len(history) < MIN_ROWS_FOR_NGBOOST:
            raise ValueError(f"only {len(history)} training rows")
        from ngboost import NGBRegressor
        from ngboost.distns import Normal

        X, cols = _feature_matrix(history)
        y = history["rentals"].to_numpy(dtype=float)
        model = NGBRegressor(Dist=Normal, n_estimators=150, learning_rate=0.05,
                             verbose=False, random_state=42)
        model.fit(X, y)
        Xf, _ = _feature_matrix(future, columns=cols)
        dist = model.pred_dist(Xf)
        locs = np.asarray(dist.params["loc"], dtype=float)
        scales = np.asarray(dist.params["scale"], dtype=float)
    except Exception as e:
        logger.info("NGBoost unavailable for tenant %s (%s) — seasonal baseline", tenant_id, e)
        model_name = "seasonal_baseline"
        stats = history.assign(cal_month=history["month"].map(lambda d: d.month)) \
            .groupby(["equipment_type", "site_id", "cal_month"])["rentals"] \
            .agg(["mean", "std"]).reset_index()
        future_cal = future.assign(cal_month=future["month"].map(lambda d: d.month))
        merged = future_cal.merge(stats, on=["equipment_type", "site_id", "cal_month"], how="left")
        overall_mean = float(history["rentals"].mean())
        locs = merged["mean"].fillna(overall_mean).to_numpy(dtype=float)
        scales = merged["std"].fillna(0.5).to_numpy(dtype=float)

    rows = [
        _row_payload(r.equipment_type, r.site_id, sites, r.month, locs[i], scales[i])
        for i, r in enumerate(future.itertuples(index=False))
    ]
    rows.sort(key=lambda r: (r["month"], -r["expected_rentals"]))
    return {"model": model_name, "horizon_months": horizon_months,
            "training_rows": int(len(history)), "rows": rows}


async def rebalancing_recommendations(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    """Greedy assignment of next month's forecasted demand to currently idle
    machines. Every recommendation carries the ₹/month idle cost it avoids."""
    forecast = await forecast_demand(db, tenant_id, horizon_months=1)
    if not forecast["rows"]:
        return {"month": None, "recommendations": [], "total_monthly_savings_inr": 0,
                "note": forecast.get("note", "No forecast available")}

    idle = (await db.execute(
        select(Equipment).where(
            Equipment.tenant_id == tenant_id,
            Equipment.status == "available",
            Equipment.disabled == False,  # noqa: E712
        )
    )).scalars().all()
    idle_by_type: dict[str, list[Equipment]] = {}
    for eq in idle:
        idle_by_type.setdefault(eq.equipment_type, []).append(eq)

    demand = sorted(forecast["rows"], key=lambda r: -r["expected_rentals"])
    recs = []
    for row in demand:
        needed = int(round(row["expected_rentals"]))
        if needed < 1 and row["prob_at_least"]["1"] >= 0.6:
            needed = 1
        pool = idle_by_type.get(row["equipment_type"], [])
        while needed > 0 and pool:
            eq = pool.pop(0)
            saving = IDLE_COST_PER_MONTH.get(eq.equipment_type, 40_000)
            recs.append({
                "equipment_code": eq.equipment_code,
                "equipment_type": eq.equipment_type,
                "move_to_site": row["site_name"],
                "site_code": row["site_code"],
                "month": row["month"],
                "expected_demand": row["expected_rentals"],
                "prob_at_least_1": row["prob_at_least"]["1"],
                "monthly_savings_inr": saving,
                "rationale": f"{int(row['prob_at_least']['1'] * 100)}% chance {row['site_code']} needs "
                             f"{max(1, int(round(row['expected_rentals'])))}+ {row['equipment_type'].lower()}(s) "
                             f"in {row['month']} — moving {eq.equipment_code} avoids "
                             f"₹{saving:,}/month in idle cost",
            })
            needed -= 1

    return {
        "month": demand[0]["month"] if demand else None,
        "model": forecast["model"],
        "recommendations": recs,
        "total_monthly_savings_inr": sum(r["monthly_savings_inr"] for r in recs),
    }

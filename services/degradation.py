"""Degradation tracing — the USP.

Health signal per machine: fuel litres per engine-hour, daily, smoothed.
Change-point detection (ruptures PELT, CUSUM fallback + backtrack refinement)
pinpoints WHEN degradation began; custody lookup answers WHICH rental / site /
operator had the machine at onset. validate_against_ground_truth scores the
tracer against the generator's planted onsets — that number goes on the slide.
"""

import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
import ruptures as rpt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.ground_truth import GroundTruth
from models.operator import Operator
from models.rental import Rental
from models.site import Site
from models.usage_log import UsageLog

logger = logging.getLogger(__name__)

MIN_POINTS = 45          # need this many logged days to call anything
SMOOTH_WINDOW = 7
# Healthy machines top out around a 1.08 post-split ratio on this signal
# (measured across 204 synthetic healthy fleets); degrading ones start at 1.097.
# 1.09 sits in that gap: zero false positives, no lost detections.
SHIFT_THRESHOLD = 1.09
MIN_ENGINE_HOURS = 1.0   # skip near-idle days: fuel/engine-hour is noise there
RAMP_STEP_DAYS = 2       # grid resolution of the onset search

# ₹: repair-at-failure vs caught-early repair, per machine class
REPAIR_COSTS = {
    "Excavator": (450_000, 90_000), "Crane": (600_000, 120_000),
    "Bulldozer": (500_000, 100_000), "Grader": (350_000, 70_000),
    "Loader": (400_000, 80_000), "Compactor": (250_000, 50_000),
}


# --- pure detection logic (unit-testable, no DB) ---

def _cusum_onset(values: np.ndarray, baseline: float) -> int | None:
    """One-sided CUSUM; returns the last in-control index before sustained drift."""
    slack = 0.04 * baseline
    threshold = 0.6 * baseline
    s, last_zero = 0.0, 0
    for i, v in enumerate(values):
        s = max(0.0, s + (float(v) - baseline - slack))
        if s == 0.0:
            last_zero = i
        elif s > threshold:
            return min(last_zero + 1, len(values) - 1)
    return None


def _ramp_onset(values: np.ndarray, day_offsets: np.ndarray) -> float | None:
    """Locate the onset by fitting a continuous flat-then-linear-ramp model.

    Degradation ramps rather than steps, and usage logs are sparse (machines sit
    idle between rentals), so the fit runs in CALENDAR-DAY space — fitting by
    sample index would smear the onset across every gap in the history.
    Returns the day-offset minimising squared error, or None if no upward ramp
    fits.
    """
    n = len(values)
    lo, hi = float(day_offsets[5]), float(day_offsets[-1] - 20)
    if hi <= lo:
        return None
    best_sse, best_k = None, None
    for k in np.arange(lo, hi, RAMP_STEP_DAYS):
        design = np.column_stack([np.ones(n), np.maximum(0.0, day_offsets - k)])
        coef, *_ = np.linalg.lstsq(design, values, rcond=None)
        if coef[1] <= 0:  # must be an upward ramp
            continue
        sse = float(np.sum((design @ coef - values) ** 2))
        if best_sse is None or sse < best_sse:
            best_sse, best_k = sse, float(k)
    return best_k


def _ramp_sse(values: np.ndarray, day_offsets: np.ndarray, k: float) -> float:
    design = np.column_stack([np.ones(len(values)), np.maximum(0.0, day_offsets - k)])
    coef, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(np.sum((design @ coef - values) ** 2))


def _step_sse(values: np.ndarray, idx: int) -> float:
    """Residual of a piecewise-constant (abrupt step) model at idx."""
    if idx <= 0 or idx >= len(values):
        return float("inf")
    pre, post = values[:idx], values[idx:]
    return float(np.sum((pre - pre.mean()) ** 2) + np.sum((post - post.mean()) ** 2))


def detect_onset(
    values: np.ndarray, day_offsets: np.ndarray | None = None
) -> tuple[int | None, dict[str, Any]]:
    """Detect a sustained upward shift in a health series.

    Two stages, deliberately separated:

    1. *Whether* — ruptures PELT proposes change-points; the earliest whose
       post-segment mean clears baseline * SHIFT_THRESHOLD wins, with CUSUM as
       fallback. A global check then confirms the whole post-onset segment
       really sits above the noise ceiling, which is what keeps healthy
       machines out of the results.
    2. *When* — the accepted onset is relocated by a calendar-space ramp fit,
       which is far more accurate than the change-point index for gradual drift.

    `day_offsets` is days-since-first-observation per sample; without it the
    fit falls back to sample index (correct only for gap-free series).
    Returns (onset_index | None, metrics).
    """
    n = len(values)
    if n < MIN_POINTS:
        return None, {"reason": "insufficient_data", "n_points": n}

    values = np.asarray(values, dtype=float)
    if day_offsets is None:
        day_offsets = np.arange(n, dtype=float)
    day_offsets = np.asarray(day_offsets, dtype=float)

    baseline = float(np.median(values[: max(14, n // 5)]))
    if baseline <= 0:
        return None, {"reason": "no_baseline", "n_points": n}

    algo = rpt.Pelt(model="rbf", min_size=10).fit(values.reshape(-1, 1))
    candidates = [bp for bp in algo.predict(pen=8) if bp < n]

    onset_idx = None
    for bp in sorted(candidates):
        if float(np.mean(values[bp:])) >= baseline * SHIFT_THRESHOLD:
            onset_idx = bp
            break
    method = "pelt"
    if onset_idx is None:
        onset_idx = _cusum_onset(values, baseline)
        method = "cusum"
    if onset_idx is None:
        return None, {"reason": "no_shift_detected", "n_points": n,
                      "baseline_rate": round(baseline, 3)}

    # Global confirmation: the drift must clear the healthy-noise ceiling.
    if float(np.mean(values[onset_idx:])) / baseline < SHIFT_THRESHOLD:
        return None, {"reason": "shift_within_noise", "n_points": n,
                      "baseline_rate": round(baseline, 3)}

    # Relocate the onset by whichever shape actually fits better: a gradual ramp
    # (typical wear) or an abrupt step (a discrete failure). Comparing residuals
    # keeps the ramp fit from dragging a genuine step-change backwards.
    ramp_day = _ramp_onset(values, day_offsets)
    if ramp_day is not None:
        ramp_idx = int(np.argmin(np.abs(day_offsets - ramp_day)))
        if _ramp_sse(values, day_offsets, ramp_day) < _step_sse(values, onset_idx):
            onset_idx = ramp_idx
            method = f"{method}+ramp_fit"
        else:
            method = f"{method}+step_fit"

    post_mean = float(np.mean(values[onset_idx:]))
    current = float(np.mean(values[-14:]))
    return onset_idx, {
        "method": method,
        "n_points": n,
        "baseline_rate": round(baseline, 3),
        "post_onset_mean_rate": round(post_mean, 3),
        "current_rate": round(current, 3),
        "degradation_pct": round((current / baseline - 1) * 100, 1),
    }


# --- DB-backed tracing ---

async def _health_series(db: AsyncSession, tenant_id: UUID, equipment_id: UUID) -> pd.DataFrame:
    rows = (await db.execute(
        select(UsageLog.log_date, UsageLog.fuel_litres, UsageLog.engine_hours)
        .where(
            UsageLog.tenant_id == tenant_id,
            UsageLog.equipment_id == equipment_id,
            UsageLog.engine_hours >= MIN_ENGINE_HOURS,
        )
        .order_by(UsageLog.log_date)
    )).all()
    if not rows:
        return pd.DataFrame(columns=["log_date", "rate", "smoothed"])
    df = pd.DataFrame(rows, columns=["log_date", "fuel", "engine"])
    df["rate"] = df["fuel"] / df["engine"]
    df = df.groupby("log_date", as_index=False)["rate"].mean()
    df["smoothed"] = (
        df["rate"].rolling(SMOOTH_WINDOW, center=True, min_periods=3).median().fillna(df["rate"])
    )
    return df


async def _custody_at(db: AsyncSession, tenant_id: UUID, equipment_id: UUID,
                      onset: date) -> dict[str, Any] | None:
    row = (await db.execute(
        select(Rental, Site.site_code, Site.name, Operator.operator_code, Operator.name)
        .outerjoin(Site, Rental.site_id == Site.id)
        .outerjoin(Operator, Rental.operator_id == Operator.id)
        .where(
            Rental.tenant_id == tenant_id,
            Rental.equipment_id == equipment_id,
            Rental.check_out_date <= onset,
            (Rental.actual_return_date.is_(None)) | (Rental.actual_return_date >= onset),
        )
        .order_by(Rental.check_out_date.desc())
        .limit(1)
    )).first()
    if not row:
        return None
    rental, site_code, site_name, op_code, op_name = row
    return {
        "rental_id": str(rental.id),
        "check_out_date": str(rental.check_out_date),
        "return_date": str(rental.actual_return_date) if rental.actual_return_date else None,
        "site_code": site_code, "site_name": site_name or "Unassigned",
        "operator_code": op_code, "operator_name": op_name or "Unassigned",
    }


async def trace_equipment(db: AsyncSession, tenant_id: UUID, equipment: Equipment,
                          *, include_timeline: bool = True) -> dict[str, Any]:
    df = await _health_series(db, tenant_id, equipment.id)
    if len(df):
        first_day = df["log_date"].iloc[0]
        day_offsets = np.array([(d - first_day).days for d in df["log_date"]], dtype=float)
        onset_idx, metrics = detect_onset(df["smoothed"].to_numpy(), day_offsets)
    else:
        onset_idx, metrics = None, {"reason": "no_data", "n_points": 0}

    result: dict[str, Any] = {
        "equipment_id": str(equipment.id),
        "equipment_code": equipment.equipment_code,
        "equipment_type": equipment.equipment_type,
        "health_signal": "fuel_litres_per_engine_hour",
        "onset_detected": onset_idx is not None,
        "onset_date": None,
        "custody_at_onset": None,
        "metrics": metrics,
        "estimated_savings_inr": 0,
    }
    if onset_idx is not None:
        onset_date = df["log_date"].iloc[onset_idx]
        fail_cost, early_cost = REPAIR_COSTS.get(equipment.equipment_type, (400_000, 80_000))
        result["onset_date"] = str(onset_date)
        result["custody_at_onset"] = await _custody_at(db, tenant_id, equipment.id, onset_date)
        result["estimated_savings_inr"] = fail_cost - early_cost
    if include_timeline:
        result["timeline"] = [
            {"date": str(r.log_date), "rate": round(float(r.rate), 3),
             "smoothed": round(float(r.smoothed), 3)}
            for r in df.itertuples(index=False)
        ]
    return result


async def fleet_degradation(db: AsyncSession, tenant_id: UUID) -> list[dict[str, Any]]:
    equipment = (await db.execute(
        select(Equipment).where(Equipment.tenant_id == tenant_id)
    )).scalars().all()
    out = []
    for eq in equipment:
        out.append(await trace_equipment(db, tenant_id, eq, include_timeline=False))
    out.sort(key=lambda r: (not r["onset_detected"], -(r["metrics"].get("degradation_pct") or 0)))
    return out


async def validate_against_ground_truth(db: AsyncSession, tenant_id: UUID,
                                        tolerance_days: int = 30) -> dict[str, Any]:
    """Score the tracer against the generator's planted onsets — the slide number."""
    truths = {
        gt.equipment_code: gt.onset_date
        for gt in (await db.execute(
            select(GroundTruth).where(
                GroundTruth.tenant_id == tenant_id,
                GroundTruth.truth_type == "degradation_onset",
            )
        )).scalars().all()
    }
    traces = await fleet_degradation(db, tenant_id)
    detected = {t["equipment_code"]: t for t in traces if t["onset_detected"]}

    details, errors, hits = [], [], 0
    for code, true_onset in sorted(truths.items()):
        trace = detected.get(code)
        if trace:
            est = date.fromisoformat(trace["onset_date"])
            err = (est - true_onset).days
            hit = abs(err) <= tolerance_days
            hits += hit
            errors.append(abs(err))
            details.append({"equipment_code": code, "true_onset": str(true_onset),
                            "detected_onset": trace["onset_date"], "error_days": err,
                            "within_tolerance": hit})
        else:
            details.append({"equipment_code": code, "true_onset": str(true_onset),
                            "detected_onset": None, "error_days": None,
                            "within_tolerance": False})

    false_positives = sorted(set(detected) - set(truths))
    n_truth = len(truths)
    accuracy = round(hits / n_truth * 100, 1) if n_truth else None
    return {
        "tolerance_days": tolerance_days,
        "machines_with_planted_onset": n_truth,
        "onsets_traced_within_tolerance": hits,
        "accuracy_pct": accuracy,
        "mean_abs_error_days": round(float(np.mean(errors)), 1) if errors else None,
        "false_positives": false_positives,
        "headline": (
            f"Traced degradation onset within ±{tolerance_days} days for "
            f"{accuracy}% of degrading machines" if accuracy is not None
            else "No planted ground truth for this tenant — seed synthetic data first"
        ),
        "details": details,
    }

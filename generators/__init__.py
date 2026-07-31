"""Synthetic fleet data generator for the Smart Rental Tracking System.

Uses numpy.random with a configurable seed for full reproducibility.
Generates equipment, sites, operators, then drives all rentals and usage
through the same service layer (checkout → log_usage → checkin) that the
API endpoints use.
"""

import logging
from datetime import date, timedelta
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.ground_truth import GroundTruth
from models.operator import Operator
from models.site import Site
from services import checkout_equipment, checkin_equipment, log_usage

logger = logging.getLogger(__name__)

PROFILES = {
    "Excavator":  {"engine": 7.0, "idle": 1.5, "fuel_rate": 12.0, "peak_month": 3},
    "Crane":      {"engine": 5.0, "idle": 2.0, "fuel_rate": 8.0,  "peak_month": 10},
    "Bulldozer":  {"engine": 8.0, "idle": 0.5, "fuel_rate": 15.0, "peak_month": 2},
    "Grader":     {"engine": 6.0, "idle": 1.0, "fuel_rate": 10.0, "peak_month": 4},
    "Loader":     {"engine": 7.0, "idle": 1.0, "fuel_rate": 11.0, "peak_month": 3},
    "Compactor":  {"engine": 5.0, "idle": 1.5, "fuel_rate": 9.0,  "peak_month": 5},
}

SITE_LOCATIONS = [
    ("Highway NH-48 Extension", "Gurugram"),
    ("Metro Line 4 Depot", "Mumbai"),
    ("Iron Ore Pit Alpha", "Bellary"),
    ("Cement Plant Expansion", "Kota"),
    ("Dam Rehabilitation", "Narmada"),
    ("Port Dredging Zone", "Mundra"),
    ("Township Grading", "Noida"),
    ("Coal Overburden Strip", "Singrauli"),
]

OPERATOR_NAMES = [
    "Rajesh Kumar", "Anil Sharma", "Vikram Singh", "Suresh Patel",
    "Manoj Yadav", "Deepak Verma", "Ramesh Gupta", "Ashok Mishra",
    "Kiran Reddy", "Ganesh Nair", "Pradeep Joshi", "Sanjay Tiwari",
    "Amit Chauhan", "Ravi Thakur", "Sunil Pandey",
]


class SyntheticFleetGenerator:
    """Generates reproducible synthetic fleet data for a tenant."""

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self._anomaly_equipment: set[str] = set()
        self._degrading_equipment: dict[str, date] = {}

    async def generate(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        num_equipment: int = 20,
        num_sites: int = 6,
        num_operators: int = 12,
        months: int = 18,
    ) -> dict:
        """Generate a full fleet dataset using the service layer."""
        logger.info("Generating synthetic fleet: %d equipment, %d sites, %d operators, %d months",
                     num_equipment, num_sites, num_operators, months)

        sites = self._make_sites(tenant_id, num_sites)
        operators = self._make_operators(tenant_id, num_operators)
        equipment_list = self._make_equipment(tenant_id, num_equipment)

        db.add_all(sites + operators + equipment_list)
        await db.flush()

        # Pick ~10% for anomalies, ~15% for degradation
        eq_codes = [e.equipment_code for e in equipment_list]
        n_anomaly = max(1, int(num_equipment * 0.10))
        n_degrade = max(1, int(num_equipment * 0.15))
        self._anomaly_equipment = {str(c) for c in self.rng.choice(eq_codes, size=n_anomaly, replace=False)}

        start_date = date.today() - timedelta(days=months * 30)
        for code in self.rng.choice(eq_codes, size=n_degrade, replace=False):
            onset_offset = int(self.rng.integers(months * 10, months * 25))
            self._degrading_equipment[str(code)] = start_date + timedelta(days=onset_offset)

        # Persist planted truths so degradation tracing can be scored against them later
        db.add_all(
            [GroundTruth(id=uuid4(), tenant_id=tenant_id, equipment_code=c, truth_type="anomaly")
             for c in sorted(self._anomaly_equipment)]
            + [GroundTruth(id=uuid4(), tenant_id=tenant_id, equipment_code=c,
                           truth_type="degradation_onset", onset_date=d)
               for c, d in sorted(self._degrading_equipment.items())]
        )

        rental_count, log_count = await self._generate_rentals(
            db, tenant_id, equipment_list, sites, operators, start_date,
        )
        await db.commit()

        summary = {
            "equipment": len(equipment_list), "sites": len(sites),
            "operators": len(operators), "rentals": rental_count, "usage_logs": log_count,
            "anomaly_equipment": sorted(self._anomaly_equipment),
            "degradation_ground_truth": {
                c: d.isoformat() for c, d in sorted(self._degrading_equipment.items())
            },
        }
        logger.info("Generation complete: %s", summary)
        return summary

    # --- entity builders ---

    def _make_sites(self, tenant_id: UUID, n: int) -> list[Site]:
        indices = self.rng.choice(len(SITE_LOCATIONS), size=min(n, len(SITE_LOCATIONS)), replace=False)
        return [
            Site(id=uuid4(), tenant_id=tenant_id, site_code=f"S{i:03d}",
                 name=SITE_LOCATIONS[idx][0], location=SITE_LOCATIONS[idx][1])
            for i, idx in enumerate(indices, 1)
        ]

    def _make_operators(self, tenant_id: UUID, n: int) -> list[Operator]:
        indices = self.rng.choice(len(OPERATOR_NAMES), size=min(n, len(OPERATOR_NAMES)), replace=False)
        return [
            Operator(id=uuid4(), tenant_id=tenant_id, operator_code=f"OP{i}",
                     name=OPERATOR_NAMES[idx])
            for i, idx in enumerate(indices, 100)
        ]

    def _make_equipment(self, tenant_id: UUID, n: int) -> list[Equipment]:
        types = list(PROFILES.keys())
        return [
            Equipment(id=uuid4(), tenant_id=tenant_id,
                      equipment_code=f"EQX{1001 + i}", equipment_type=types[i % len(types)])
            for i in range(n)
        ]

    # --- rental generation via service layer ---

    def _seasonality_factor(self, eq_type: str, month: int) -> float:
        peak = PROFILES[eq_type]["peak_month"]
        dist = min(abs(month - peak), 12 - abs(month - peak))
        return 1.0 + 0.5 * np.cos(dist * np.pi / 6)

    async def _generate_rentals(
        self, db: AsyncSession, tenant_id: UUID,
        equipment: list[Equipment], sites: list[Site], operators: list[Operator],
        start_date: date,
    ) -> tuple[int, int]:
        rental_count = 0
        log_count = 0
        end_date = date.today()

        for eq in equipment:
            profile = PROFILES[eq.equipment_type]
            is_anomaly = eq.equipment_code in self._anomaly_equipment
            degrade_onset = self._degrading_equipment.get(eq.equipment_code)
            cursor = start_date

            while cursor < end_date:
                season = self._seasonality_factor(eq.equipment_type, cursor.month)
                if self.rng.random() > 0.3 * season:
                    cursor += timedelta(days=int(self.rng.integers(5, 20)))
                    continue

                duration = int(self.rng.integers(7, 45))
                expected_return = cursor + timedelta(days=duration)
                overdue_days = int(self.rng.integers(1, 11)) if self.rng.random() < 0.12 else 0
                actual_return = min(expected_return + timedelta(days=overdue_days), end_date)
                returned = actual_return <= end_date - timedelta(days=1)

                site = self.rng.choice(sites) if not (is_anomaly and self.rng.random() < 0.30) else None
                op = self.rng.choice(operators) if not (is_anomaly and self.rng.random() < 0.30) else None

                # --- USE SERVICE LAYER ---
                rental = await checkout_equipment(
                    db, tenant_id, eq.equipment_code,
                    site_id=site.id if site else None,
                    operator_id=op.id if op else None,
                    expected_return_date=expected_return,
                    check_out_date=cursor,
                )
                rental_count += 1

                # Log daily usage
                log_end = actual_return if returned else min(end_date, expected_return)
                day = cursor
                while day <= log_end:
                    engine_h, idle_h, fuel = self._daily_usage(profile, eq.equipment_code, day, is_anomaly, degrade_onset)
                    await log_usage(
                        db, tenant_id, rental.id, eq.id, day,
                        engine_h, idle_h, fuel,
                        site_id=site.id if site else None,
                        operator_id=op.id if op else None,
                    )
                    log_count += 1
                    day += timedelta(days=1)

                # Checkin via service layer
                if not returned:
                    # Machine is still out as of today — that's this machine's end
                    # state. Looping again would try to check out a rented machine.
                    break
                await checkin_equipment(
                    db, tenant_id, eq.equipment_code,
                    actual_return_date=actual_return,
                )

                cursor = actual_return + timedelta(days=int(self.rng.integers(1, 8)))

        logger.info("Generated %d rentals, %d usage logs via service layer", rental_count, log_count)
        return rental_count, log_count

    def _daily_usage(
        self, profile: dict, eq_code: str, day: date,
        is_anomaly: bool, degrade_onset: date | None,
    ) -> tuple[float, float, float]:
        base_engine = profile["engine"]
        base_idle = profile["idle"]
        fuel_rate = profile["fuel_rate"]

        engine_h = max(0, self.rng.normal(base_engine, base_engine * 0.15))
        idle_h = max(0, self.rng.normal(base_idle, base_idle * 0.3))

        if is_anomaly and self.rng.random() < 0.25:
            engine_h, idle_h = idle_h * 0.5, engine_h + idle_h

        fuel_mult = 1.0
        if degrade_onset and day >= degrade_onset:
            fuel_mult = 1.0 + 0.002 * (day - degrade_onset).days

        fuel = round(engine_h * fuel_rate * fuel_mult * self.rng.uniform(0.9, 1.1), 2)
        return round(engine_h, 2), round(idle_h, 2), fuel

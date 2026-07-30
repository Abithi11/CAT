"""Synthetic fleet data generator for the Smart Rental Tracking System.

Uses numpy.random with a configurable seed for full reproducibility.
Generates equipment, sites, operators, rental history, and daily usage logs
with planted seasonality, anomalies, and degradation patterns.
"""

import logging
from datetime import date, timedelta
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from models.equipment import Equipment
from models.operator import Operator
from models.rental import Rental
from models.site import Site
from models.usage_log import UsageLog

logger = logging.getLogger(__name__)

# Equipment type profiles: base daily engine/idle hours, fuel per engine-hour, seasonality peak month
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
        self._anomaly_equipment: set[UUID] = set()
        self._degrading_equipment: dict[UUID, date] = {}

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
        """Generate a full fleet dataset and persist to DB.

        Returns a summary dict with counts of all generated records.
        """
        logger.info("Generating synthetic fleet: %d equipment, %d sites, %d operators, %d months",
                     num_equipment, num_sites, num_operators, months)

        sites = self._make_sites(tenant_id, num_sites)
        operators = self._make_operators(tenant_id, num_operators)
        equipment_list = self._make_equipment(tenant_id, num_equipment)

        db.add_all(sites + operators + equipment_list)
        await db.flush()

        # Pick ~10% of equipment for anomalies, ~15% for degradation
        eq_ids = [e.id for e in equipment_list]
        n_anomaly = max(1, int(num_equipment * 0.10))
        n_degrade = max(1, int(num_equipment * 0.15))
        self._anomaly_equipment = set(self.rng.choice(eq_ids, size=n_anomaly, replace=False))

        start_date = date.today() - timedelta(days=months * 30)
        degrade_ids = self.rng.choice(eq_ids, size=n_degrade, replace=False)
        for eid in degrade_ids:
            onset_offset = int(self.rng.integers(months * 10, months * 25))
            self._degrading_equipment[eid] = start_date + timedelta(days=onset_offset)

        rentals, usage_logs = self._make_rentals_and_logs(
            tenant_id, equipment_list, sites, operators, start_date, months,
        )

        db.add_all(rentals)
        await db.flush()
        db.add_all(usage_logs)
        await db.commit()

        summary = {
            "equipment": len(equipment_list),
            "sites": len(sites),
            "operators": len(operators),
            "rentals": len(rentals),
            "usage_logs": len(usage_logs),
        }
        logger.info("Generation complete: %s", summary)
        return summary

    # --- builders ---

    def _make_sites(self, tenant_id: UUID, n: int) -> list[Site]:
        indices = self.rng.choice(len(SITE_LOCATIONS), size=min(n, len(SITE_LOCATIONS)), replace=False)
        sites = []
        for i, idx in enumerate(indices, 1):
            name, location = SITE_LOCATIONS[idx]
            sites.append(Site(
                id=uuid4(), tenant_id=tenant_id,
                site_code=f"S{i:03d}", name=name, location=location,
            ))
            logger.debug("Created site %s: %s", sites[-1].site_code, name)
        return sites

    def _make_operators(self, tenant_id: UUID, n: int) -> list[Operator]:
        indices = self.rng.choice(len(OPERATOR_NAMES), size=min(n, len(OPERATOR_NAMES)), replace=False)
        ops = []
        for i, idx in enumerate(indices, 100):
            ops.append(Operator(
                id=uuid4(), tenant_id=tenant_id,
                operator_code=f"OP{i}", name=OPERATOR_NAMES[idx],
            ))
            logger.debug("Created operator %s: %s", ops[-1].operator_code, OPERATOR_NAMES[idx])
        return ops

    def _make_equipment(self, tenant_id: UUID, n: int) -> list[Equipment]:
        types = list(PROFILES.keys())
        equipment = []
        for i in range(n):
            eq_type = types[i % len(types)]
            equipment.append(Equipment(
                id=uuid4(), tenant_id=tenant_id,
                equipment_code=f"EQX{1001 + i}", equipment_type=eq_type,
                status="available",
            ))
            logger.debug("Created equipment %s (%s)", equipment[-1].equipment_code, eq_type)
        return equipment

    def _seasonality_factor(self, eq_type: str, month: int) -> float:
        """Returns a multiplier 0.5–1.5 based on how close `month` is to the peak."""
        peak = PROFILES[eq_type]["peak_month"]
        dist = min(abs(month - peak), 12 - abs(month - peak))
        return 1.0 + 0.5 * np.cos(dist * np.pi / 6)  # peaks at 1.5, troughs at 0.5

    def _make_rentals_and_logs(
        self, tenant_id: UUID, equipment: list[Equipment],
        sites: list[Site], operators: list[Operator],
        start_date: date, months: int,
    ) -> tuple[list[Rental], list[UsageLog]]:
        all_rentals: list[Rental] = []
        all_logs: list[UsageLog] = []

        for eq in equipment:
            profile = PROFILES[eq.equipment_type]
            cursor = start_date
            end_date = date.today()
            is_anomaly = eq.id in self._anomaly_equipment
            degrade_onset = self._degrading_equipment.get(eq.id)

            while cursor < end_date:
                # Probability of starting a rental this week, modulated by season
                season = self._seasonality_factor(eq.equipment_type, cursor.month)
                if self.rng.random() > 0.3 * season:
                    cursor += timedelta(days=int(self.rng.integers(5, 20)))
                    continue

                duration = int(self.rng.integers(7, 45))
                checkout = cursor
                expected_return = checkout + timedelta(days=duration)

                # 12% chance of overdue (returned 1–10 days late)
                overdue_days = int(self.rng.integers(1, 11)) if self.rng.random() < 0.12 else 0
                actual_return = min(expected_return + timedelta(days=overdue_days), end_date)
                returned = actual_return <= end_date - timedelta(days=1)

                # Anomaly: ~30% of anomaly-equipment rentals have NULL site or operator
                site = self.rng.choice(sites) if not (is_anomaly and self.rng.random() < 0.30) else None
                op = self.rng.choice(operators) if not (is_anomaly and self.rng.random() < 0.30) else None

                rental_id = uuid4()
                status = "returned" if returned else "active"
                if returned and overdue_days > 0:
                    status = "returned"  # was overdue but returned

                rental = Rental(
                    id=rental_id, tenant_id=tenant_id, equipment_id=eq.id,
                    site_id=site.id if site else None,
                    operator_id=op.id if op else None,
                    check_out_date=checkout, expected_return_date=expected_return,
                    actual_return_date=actual_return if returned else None,
                    status=status,
                )
                all_rentals.append(rental)
                logger.debug("Rental %s: %s at %s, %s–%s (%s)",
                             eq.equipment_code, eq.equipment_type,
                             site.site_code if site else "NO_SITE",
                             checkout, actual_return if returned else "ongoing", status)

                # Generate daily usage logs
                log_end = actual_return if returned else min(end_date, expected_return)
                day = checkout
                while day <= log_end:
                    engine_h, idle_h, fuel = self._daily_usage(
                        profile, eq.id, day, is_anomaly, degrade_onset,
                    )
                    all_logs.append(UsageLog(
                        id=uuid4(), tenant_id=tenant_id, rental_id=rental_id,
                        equipment_id=eq.id,
                        site_id=site.id if site else None,
                        operator_id=op.id if op else None,
                        log_date=day, engine_hours=engine_h,
                        idle_hours=idle_h, fuel_litres=fuel,
                    ))
                    day += timedelta(days=1)

                cursor = (actual_return if returned else expected_return) + timedelta(days=int(self.rng.integers(1, 8)))

        logger.info("Generated %d rentals, %d usage logs", len(all_rentals), len(all_logs))
        return all_rentals, all_logs

    def _daily_usage(
        self, profile: dict, eq_id: UUID, day: date,
        is_anomaly: bool, degrade_onset: date | None,
    ) -> tuple[float, float, float]:
        """Generate a single day's engine hours, idle hours, and fuel."""
        base_engine = profile["engine"]
        base_idle = profile["idle"]
        fuel_rate = profile["fuel_rate"]

        # Normal noise
        engine_h = max(0, self.rng.normal(base_engine, base_engine * 0.15))
        idle_h = max(0, self.rng.normal(base_idle, base_idle * 0.3))

        # Anomaly: swap engine and idle (machine sits idle most of the day)
        if is_anomaly and self.rng.random() < 0.25:
            engine_h, idle_h = idle_h * 0.5, engine_h + idle_h

        # Degradation: fuel efficiency worsens linearly after onset
        fuel_mult = 1.0
        if degrade_onset and day >= degrade_onset:
            days_since = (day - degrade_onset).days
            fuel_mult = 1.0 + 0.002 * days_since  # +0.2% per day

        fuel = round(engine_h * fuel_rate * fuel_mult * self.rng.uniform(0.9, 1.1), 2)
        return round(engine_h, 2), round(idle_h, 2), fuel

"""Tests for the synthetic fleet data generator."""

import pytest
from uuid import uuid4

from generators import SyntheticFleetGenerator


class TestGeneratorUnit:
    """Pure unit tests — determinism + data shapes, no DB."""

    def test_same_seed_same_output(self):
        g1 = SyntheticFleetGenerator(seed=99)
        g2 = SyntheticFleetGenerator(seed=99)
        tid = uuid4()
        sites1 = g1._make_sites(tid, 4)
        sites2 = g2._make_sites(tid, 4)
        assert [s.site_code for s in sites1] == [s.site_code for s in sites2]
        assert [s.name for s in sites1] == [s.name for s in sites2]

    def test_different_seed_different_output(self):
        g1 = SyntheticFleetGenerator(seed=1)
        g2 = SyntheticFleetGenerator(seed=2)
        tid = uuid4()
        names1 = {s.name for s in g1._make_sites(tid, 6)}
        names2 = {s.name for s in g2._make_sites(tid, 6)}
        # With 8 possible sites and 6 chosen, different seeds should (almost certainly) differ
        assert names1 != names2

    def test_equipment_types_cycle(self):
        g = SyntheticFleetGenerator(seed=42)
        eq = g._make_equipment(uuid4(), 12)
        types = [e.equipment_type for e in eq]
        # 6 types cycling: first 6 should match second 6
        assert types[:6] == types[6:]

    def test_equipment_codes_unique(self):
        g = SyntheticFleetGenerator(seed=42)
        eq = g._make_equipment(uuid4(), 30)
        codes = [e.equipment_code for e in eq]
        assert len(codes) == len(set(codes))

    def test_operator_count_capped(self):
        g = SyntheticFleetGenerator(seed=42)
        ops = g._make_operators(uuid4(), 100)
        assert len(ops) == 15  # capped at len(OPERATOR_NAMES)

    def test_seasonality_peak(self):
        g = SyntheticFleetGenerator(seed=42)
        # Excavator peaks in month 3
        peak = g._seasonality_factor("Excavator", 3)
        trough = g._seasonality_factor("Excavator", 9)
        assert peak > trough
        assert peak == pytest.approx(1.5, abs=0.01)
        assert trough == pytest.approx(0.5, abs=0.01)


class TestGeneratorIntegration:
    """Integration tests — generate data and check DB contents."""

    async def test_generate_creates_records(self, engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from sqlalchemy import func, select
        from models.equipment import Equipment
        from models.site import Site
        from models.operator import Operator
        from models.rental import Rental
        from models.usage_log import UsageLog
        from models.tenant import Tenant

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            tenant = Tenant(id=uuid4(), name="GenTest", slug="gentest", is_active=True)
            db.add(tenant)
            await db.flush()

            gen = SyntheticFleetGenerator(seed=42)
            summary = await gen.generate(
                db, tenant.id,
                num_equipment=6, num_sites=3, num_operators=4, months=6,
            )

            assert summary["equipment"] == 6
            assert summary["sites"] == 3
            assert summary["operators"] == 4
            assert summary["rentals"] > 0
            assert summary["usage_logs"] > 0

            # Verify actual DB row counts match summary
            for model, key in [(Equipment, "equipment"), (Site, "sites"),
                                (Operator, "operators"), (Rental, "rentals"),
                                (UsageLog, "usage_logs")]:
                count = await db.scalar(select(func.count()).select_from(model))
                assert count == summary[key], f"{key}: expected {summary[key]}, got {count}"

    async def test_deterministic_across_runs(self, engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from models.tenant import Tenant

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as db:
            t = Tenant(id=uuid4(), name="Det1", slug="det1", is_active=True)
            db.add(t)
            await db.flush()
            s1 = await SyntheticFleetGenerator(seed=77).generate(
                db, t.id, num_equipment=4, num_sites=2, num_operators=3, months=3,
            )

        # Drop and recreate for a clean run
        from utils.database import Base
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.drop_all)
            await c.run_sync(Base.metadata.create_all)

        async with factory() as db:
            t = Tenant(id=uuid4(), name="Det2", slug="det2", is_active=True)
            db.add(t)
            await db.flush()
            s2 = await SyntheticFleetGenerator(seed=77).generate(
                db, t.id, num_equipment=4, num_sites=2, num_operators=3, months=3,
            )

        assert s1 == s2

    async def test_anomalies_planted(self, engine):
        """At least some rentals should have NULL site or operator."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from sqlalchemy import select, func
        from models.rental import Rental
        from models.tenant import Tenant

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            t = Tenant(id=uuid4(), name="Anom", slug="anomtest", is_active=True)
            db.add(t)
            await db.flush()
            await SyntheticFleetGenerator(seed=42).generate(
                db, t.id, num_equipment=20, num_sites=5, num_operators=8, months=12,
            )
            null_site = await db.scalar(
                select(func.count()).select_from(Rental).where(Rental.site_id.is_(None))
            )
            null_op = await db.scalar(
                select(func.count()).select_from(Rental).where(Rental.operator_id.is_(None))
            )
            assert null_site > 0 or null_op > 0, "Expected anomaly rentals with NULL site/operator"

    async def test_seed_endpoint(self, client, engine):
        """Register a tenant, then hit /seed to generate data."""
        reg = await client.post("/auth/register", json={
            "tenant_name": "SeedCo", "tenant_slug": "seedco",
            "email": "admin@seedco.com", "password": "pass123",
        })
        token = reg.json()["access_token"]

        resp = await client.post(
            "/seed", json={"seed": 42, "num_equipment": 5, "num_sites": 2, "num_operators": 3, "months": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "Synthetic data generated"
        assert data["summary"]["equipment"] == 5
        assert data["summary"]["sites"] == 2
        assert data["summary"]["rentals"] > 0
        assert data["summary"]["usage_logs"] > 0
        assert data["summary"]["degradation_ground_truth"]
        assert data["summary"]["anomaly_equipment"]

    async def test_ground_truth_persisted(self, engine):
        """Planted degradation onsets must survive in the ground_truth table for Phase 4 scoring."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from sqlalchemy import select
        from models.ground_truth import GroundTruth
        from models.tenant import Tenant

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            t = Tenant(id=uuid4(), name="Truth", slug="truthtest", is_active=True)
            db.add(t)
            await db.flush()
            summary = await SyntheticFleetGenerator(seed=42).generate(
                db, t.id, num_equipment=10, num_sites=3, num_operators=4, months=6,
            )

            rows = (await db.execute(
                select(GroundTruth).where(GroundTruth.tenant_id == t.id)
            )).scalars().all()

            onsets = {r.equipment_code: r.onset_date.isoformat()
                      for r in rows if r.truth_type == "degradation_onset"}
            assert onsets == summary["degradation_ground_truth"]

            anomalies = {r.equipment_code for r in rows if r.truth_type == "anomaly"}
            assert anomalies == set(summary["anomaly_equipment"])
            for r in rows:
                if r.truth_type == "anomaly":
                    assert r.onset_date is None

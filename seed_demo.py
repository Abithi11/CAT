"""Idempotent demo seeding — runs before uvicorn in the docker-compose command.

Waits for Postgres, creates the schema, enables TimescaleDB, then (only if the
demo tenant doesn't already exist) creates a demo tenant + login and generates
the full synthetic fleet. One command = running system with demo data.
"""

import asyncio
import logging
import sys

from passlib.context import CryptContext

import main  # noqa: F401 – imports every model so Base.metadata is complete
from generators import SyntheticFleetGenerator
from models.config import settings
from models.tenant import Tenant
from models.user import User
from utils.database import AsyncSessionLocal, Base, apply_timescale, engine

from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_demo")


async def wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect():
                return
        except Exception as e:
            logger.info("Waiting for database (%d/%d): %s", attempt, retries, e)
            await asyncio.sleep(delay)
    logger.error("Database never became reachable")
    sys.exit(1)


async def seed() -> None:
    await wait_for_db()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_timescale(engine)

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(Tenant).where(Tenant.slug == settings.demo_tenant_slug)
        )).scalar_one_or_none()
        if existing:
            logger.info("Demo tenant '%s' already seeded — skipping", settings.demo_tenant_slug)
            return

        tenant = Tenant(name=settings.demo_tenant_name,
                        slug=settings.demo_tenant_slug, is_active=True)
        db.add(tenant)
        await db.flush()
        pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
        db.add(User(
            tenant_id=tenant.id, email=settings.demo_email,
            hashed_password=pwd.hash(settings.demo_password),
            full_name="Demo Dealer", is_active=True,
        ))
        await db.flush()

        summary = await SyntheticFleetGenerator(seed=42).generate(
            db, tenant.id, num_equipment=20, num_sites=6, num_operators=12, months=18,
        )
        logger.info("Seeded demo fleet: %s", summary)
        logger.info("Demo login → tenant: %s | email: %s | password: %s",
                    settings.demo_tenant_slug, settings.demo_email, settings.demo_password)


if __name__ == "__main__":
    asyncio.run(seed())

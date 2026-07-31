import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.config import settings
from utils.database import Base, apply_timescale, engine, get_db
from models.tenant import Tenant  # noqa: F401 – registers table with Base.metadata
from models.user import User  # noqa: F401 – registers table with Base.metadata
from models.equipment import Equipment  # noqa: F401
from models.site import Site  # noqa: F401
from models.operator import Operator  # noqa: F401
from models.rental import Rental  # noqa: F401
from models.usage_log import UsageLog  # noqa: F401
from models.ground_truth import GroundTruth  # noqa: F401
from models.alert import Alert  # noqa: F401
from models.case_file import CaseFile  # noqa: F401
from routers.login import login_router
from routers.register import register_router
from routers.rentals import rentals_router
from routers.seed import seed_router
from routers.analytics import analytics_router
from routers.dashboard import dashboard_router
from routers.alerts import alerts_router
from routers.reports import reports_router
from routers.forecast import forecast_router
from routers.degradation import degradation_router
from routers.agent import agent_router
from routers.equipment import equipment_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_timescale(engine)

    from services.llm import probe
    await probe()

    scheduler = None
    if settings.scheduler_enabled:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.alerts import scan_all_tenants

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            scan_all_tenants, "interval",
            minutes=settings.alert_scan_interval_minutes,
            next_run_time=datetime.now(),  # first scan right after startup
        )
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="CAT - Smart Rental Tracking", lifespan=lifespan)


@app.get("/health", tags=["health"])
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


app.include_router(login_router)
app.include_router(register_router)
app.include_router(rentals_router)
app.include_router(seed_router)
app.include_router(analytics_router)
app.include_router(dashboard_router)
app.include_router(alerts_router)
app.include_router(reports_router)
app.include_router(forecast_router)
app.include_router(degradation_router)
app.include_router(agent_router)
app.include_router(equipment_router)

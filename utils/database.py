import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from models.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def apply_timescale(target_engine) -> bool:
    """Best-effort: enable TimescaleDB and convert usage_logs to a hypertable.

    Returns False (and keeps the plain table) when running against vanilla
    Postgres, so the app works either way.
    """
    try:
        async with target_engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            await conn.execute(text(
                "SELECT create_hypertable('usage_logs', 'log_date', "
                "if_not_exists => TRUE, migrate_data => TRUE)"
            ))
        logger.info("TimescaleDB enabled: usage_logs is a hypertable")
        return True
    except Exception as e:
        logger.warning("TimescaleDB not enabled (plain Postgres?): %s", e)
        return False
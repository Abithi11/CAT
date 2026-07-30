from contextlib import asynccontextmanager

from fastapi import FastAPI

from utils.database import Base, engine
from models.tenant import Tenant  # noqa: F401 – registers table with Base.metadata
from models.user import User  # noqa: F401 – registers table with Base.metadata
from routers.login import login_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="CAT - Smart Rental Tracking", lifespan=lifespan)

app.include_router(login_router)

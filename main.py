from contextlib import asynccontextmanager

from fastapi import FastAPI

from utils.database import Base, engine
from models.tenant import Tenant  # noqa: F401 – registers table with Base.metadata
from models.user import User  # noqa: F401 – registers table with Base.metadata
from models.equipment import Equipment  # noqa: F401
from models.site import Site  # noqa: F401
from models.operator import Operator  # noqa: F401
from models.rental import Rental  # noqa: F401
from models.usage_log import UsageLog  # noqa: F401
from routers.login import login_router
from routers.register import register_router
from routers.rentals import rentals_router
from routers.seed import seed_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="CAT - Smart Rental Tracking", lifespan=lifespan)

app.include_router(login_router)
app.include_router(register_router)
app.include_router(rentals_router)
app.include_router(seed_router)

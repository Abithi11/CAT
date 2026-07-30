from pydantic import BaseModel
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from generators import SyntheticFleetGenerator
from models.user import User
from utils.database import get_db

seed_router = APIRouter(prefix="/seed", tags=["seed"])


class SeedRequest(BaseModel):
    seed: int = 42
    num_equipment: int = 20
    num_sites: int = 6
    num_operators: int = 12
    months: int = 18


class SeedResponse(BaseModel):
    message: str
    summary: dict


@seed_router.post("", response_model=SeedResponse, status_code=status.HTTP_201_CREATED)
async def seed_data(
    body: SeedRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate synthetic fleet data for the current user's tenant."""
    gen = SyntheticFleetGenerator(seed=body.seed)
    summary = await gen.generate(
        db, user.tenant_id,
        num_equipment=body.num_equipment,
        num_sites=body.num_sites,
        num_operators=body.num_operators,
        months=body.months,
    )
    return SeedResponse(message="Synthetic data generated", summary=summary)

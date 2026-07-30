from fastapi import APIRouter, HTTPException, Depends, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import create_access_token, create_refresh_token
from models.auth import RegisterRequest, TokenResponse
from models.tenant import Tenant
from models.user import User
from utils.database import get_db

register_router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@register_router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant slug already exists")

    tenant = Tenant(name=body.tenant_name, slug=body.tenant_slug, is_active=True)
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id, email=body.email,
        hashed_password=pwd_context.hash(body.password),
        full_name=body.full_name, is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id, tenant.id, user.email),
        refresh_token=create_refresh_token(user.id, tenant.id),
    )

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.jwt import create_access_token, create_refresh_token, decode_token
from utils.database import get_db
from models.tenant import Tenant
from models.user import User
from models.auth import LoginRequest, TokenResponse, RefreshRequest, UserResponse

login_router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def _first(db: AsyncSession, stmt, *, detail: str, code: int = 401):
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=code, detail=detail)
    return row


def _issue_tokens(user, tenant):
    return TokenResponse(
        access_token=create_access_token(user.id, tenant.id, user.email),
        refresh_token=create_refresh_token(user.id, tenant.id),
    )


@login_router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    tenant = await _first(
        db,
        select(Tenant).where(Tenant.slug == body.tenant_slug, Tenant.is_active == True),
        detail="Tenant not found", code=404,
    )
    user = await _first(
        db,
        select(User).where(User.tenant_id == tenant.id, User.email == body.email, User.is_active == True),
        detail="Invalid credentials",
    )
    if not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _issue_tokens(user, tenant)


@login_router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await _first(db, select(User).where(User.id == payload["sub"]), detail="User not found or inactive")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    tenant = await _first(
        db, select(Tenant).where(Tenant.id == payload["tenant_id"]), detail="Tenant not active",
    )
    if not tenant.is_active:
        raise HTTPException(status_code=401, detail="Tenant not active")
    return _issue_tokens(user, tenant)


@login_router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user

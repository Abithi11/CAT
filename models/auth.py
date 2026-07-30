from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    tenant_slug: str
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    tenant_name: str
    tenant_slug: str
    email: EmailStr
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    is_active: bool
    tenant_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}

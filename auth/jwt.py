from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt

from models.config import settings


def _make_token(data: dict, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {**data, "exp": now + expires_delta, "iat": now},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user_id: UUID, tenant_id: UUID, email: str) -> str:
    return _make_token(
        {"sub": str(user_id), "tenant_id": str(tenant_id), "email": email, "type": "access"},
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(user_id: UUID, tenant_id: UUID) -> str:
    return _make_token(
        {"sub": str(user_id), "tenant_id": str(tenant_id), "type": "refresh"},
        timedelta(days=settings.jwt_refresh_token_expire_days),
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

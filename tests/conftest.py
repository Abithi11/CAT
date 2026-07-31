from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from main import app
from models.tenant import Tenant
from models.user import User
from utils.database import Base, get_db

import os

PG_SERVER = os.environ.get(
    "TEST_PG_SERVER", "postgresql+asyncpg://postgres:postgres@localhost:5432"
)
TEST_DB_NAME = "cat_test"
TEST_DB = f"{PG_SERVER}/{TEST_DB_NAME}"
PWD = CryptContext(schemes=["bcrypt"], deprecated="auto")
HASHED = PWD.hash("password123")


@pytest_asyncio.fixture(scope="session")
async def _ensure_test_db():
    """Create the test database if it doesn't already exist."""
    tmp = create_async_engine(f"{PG_SERVER}/postgres", isolation_level="AUTOCOMMIT")
    async with tmp.connect() as conn:
        exists = await conn.scalar(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DB_NAME}'")
        )
        if not exists:
            await conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    await tmp.dispose()


@pytest_asyncio.fixture
async def engine(_ensure_test_db):
    e = create_async_engine(TEST_DB)
    async with e.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield e
    async with e.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
    await e.dispose()


@pytest_asyncio.fixture
async def seed(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    tenants = {s: Tenant(id=uuid4(), name=s.title(), slug=s, is_active=a)
               for s, a in [("alpha", True), ("beta", True), ("gamma", False)]}

    users_spec = [
        ("alice", "alpha", "alice@test.com", "Alice", True),
        ("bob", "beta", "bob@test.com", "Bob", True),
        ("charlie", "alpha", "charlie@test.com", "Charlie", False),
        ("alice_beta", "beta", "alice@test.com", "Alice in Beta", True),
    ]
    users = {
        key: User(id=uuid4(), tenant_id=tenants[t].id, email=e, hashed_password=HASHED, full_name=n, is_active=a)
        for key, t, e, n, a in users_spec
    }
    async with factory() as session:
        session.add_all([*tenants.values(), *users.values()])
        await session.commit()
    return {"tenants": tenants, "users": users}


@pytest_asyncio.fixture
async def client(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

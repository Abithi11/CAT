"""Tests for multi-tenant auth: login, tenant isolation, JWT validation, and refresh."""

import pytest
from auth.jwt import decode_token

LOGIN = "/auth/login"
PW = "password123"


async def _login(client, slug="alpha", email="alice@test.com", pw=PW):
    return await client.post(LOGIN, json={"tenant_slug": slug, "email": email, "password": pw})


class TestLogin:
    async def test_login_success(self, client, seed):
        resp = await _login(client)
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_type"] == "bearer"
        payload = decode_token(data["access_token"])
        assert payload["email"] == "alice@test.com"
        assert payload["tenant_id"] == str(seed["tenants"]["alpha"].id)

    @pytest.mark.parametrize("slug,email,pw,code,detail", [
        ("nonexistent", "alice@test.com", PW, 404, "Tenant not found"),
        ("gamma", "alice@test.com", PW, 404, "Tenant not found"),
        ("alpha", "alice@test.com", "wrong", 401, "Invalid credentials"),
        ("alpha", "charlie@test.com", PW, 401, "Invalid credentials"),
    ])
    async def test_login_errors(self, client, seed, slug, email, pw, code, detail):
        resp = await _login(client, slug, email, pw)
        assert resp.status_code == code
        assert resp.json()["detail"] == detail

    async def test_tenant_isolation(self, client, seed):
        """Same email in different tenants logs in as separate users."""
        ra, rb = await _login(client, "alpha"), await _login(client, "beta")
        ta = decode_token(ra.json()["access_token"])
        tb = decode_token(rb.json()["access_token"])
        assert ta["sub"] == str(seed["users"]["alice"].id)
        assert tb["sub"] == str(seed["users"]["alice_beta"].id)
        assert ta["sub"] != tb["sub"]


class TestMe:
    async def _token(self, client):
        return (await _login(client)).json()["access_token"]

    async def test_me_success(self, client, seed):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {await self._token(client)}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "alice@test.com"
        assert data["full_name"] == "Alice"

    async def test_me_no_token(self, client, seed):
        assert (await client.get("/auth/me")).status_code == 401

    async def test_me_invalid_token(self, client, seed):
        r = await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401

    async def test_me_expired_token(self, client, seed):
        from datetime import datetime, timedelta, timezone
        from jose import jwt
        from models.config import settings

        expired = jwt.encode(
            {"sub": str(seed["users"]["alice"].id), "tenant_id": str(seed["tenants"]["alpha"].id),
             "email": "alice@test.com", "type": "access",
             "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
             "iat": datetime.now(timezone.utc) - timedelta(hours=1)},
            settings.jwt_secret, algorithm=settings.jwt_algorithm,
        )
        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401


class TestRefresh:
    async def _refresh_tok(self, client):
        return (await _login(client)).json()["refresh_token"]

    async def test_refresh_success(self, client, seed):
        resp = await client.post("/auth/refresh", json={"refresh_token": await self._refresh_tok(client)})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data and data["token_type"] == "bearer"

    async def test_refresh_invalid(self, client, seed):
        resp = await client.post("/auth/refresh", json={"refresh_token": "garbage"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid refresh token"

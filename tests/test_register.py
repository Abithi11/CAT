"""Tests for the registration endpoint."""

import pytest


class TestRegister:
    async def test_register_success(self, client, engine):
        resp = await client.post("/auth/register", json={
            "tenant_name": "NewCo", "tenant_slug": "newco",
            "email": "admin@newco.com", "password": "secret123", "full_name": "Admin",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_register_duplicate_slug(self, client, seed):
        resp = await client.post("/auth/register", json={
            "tenant_name": "Alpha Again", "tenant_slug": "alpha",
            "email": "new@alpha.com", "password": "pass",
        })
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Tenant slug already exists"

    async def test_register_then_login(self, client, engine):
        await client.post("/auth/register", json={
            "tenant_name": "TestCo", "tenant_slug": "testco",
            "email": "user@testco.com", "password": "mypass", "full_name": "Test User",
        })
        resp = await client.post("/auth/login", json={
            "tenant_slug": "testco", "email": "user@testco.com", "password": "mypass",
        })
        assert resp.status_code == 200
        assert resp.json()["token_type"] == "bearer"

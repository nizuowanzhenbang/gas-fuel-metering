"""认证 router 集成测试。"""
from __future__ import annotations


def test_login_success_returns_bearer_token(client, session_factory):
    from backend.auth import Role
    from backend.tests.conftest import _create_user

    _create_user(session_factory, "admin", "admin123", Role.ADMIN)
    r = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["role"] == "ADMIN"
    assert body["username"] == "admin"


def test_login_wrong_password_returns_401(client, session_factory):
    from backend.auth import Role
    from backend.tests.conftest import _create_user

    _create_user(session_factory, "admin", "admin123", Role.ADMIN)
    r = client.post("/api/auth/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert "invalid" in r.json()["detail"]


def test_protected_endpoint_without_token_returns_401(client):
    r = client.get("/api/gas-sources")
    assert r.status_code == 401

"""账户管理 router 集成测试。"""
from __future__ import annotations


def _create_payload(username: str = "alice", role: str = "OPERATOR") -> dict:
    return {
        "username": username,
        "password": "secret123",
        "full_name": username.title(),
        "role": role,
    }


def test_create_get_list_update_full_flow(client, admin_headers):
    r = client.post("/api/users", json=_create_payload(), headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    uid = body["id"]
    assert body["username"] == "alice"
    assert body["role"] == "OPERATOR"
    assert body["is_active"] is True
    assert "password" not in body and "password_hash" not in body

    r = client.get(f"/api/users/{uid}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Alice"

    r = client.get("/api/users", headers=admin_headers)
    assert r.status_code == 200
    # 列表包含 fixture 建的 admin + 新建的 alice
    assert r.json()["total"] == 2

    r = client.patch(
        f"/api/users/{uid}",
        json={"full_name": "Alice K.", "role": "METER_ENG"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Alice K."
    assert r.json()["role"] == "METER_ENG"


def test_create_duplicate_username_returns_409(client, admin_headers):
    client.post("/api/users", json=_create_payload(), headers=admin_headers)
    r = client.post("/api/users", json=_create_payload(), headers=admin_headers)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_reset_password_lets_new_password_login(client, admin_headers):
    r = client.post("/api/users", json=_create_payload(), headers=admin_headers)
    uid = r.json()["id"]

    # 旧密码先证明能登录
    r = client.post("/api/auth/login", data={"username": "alice", "password": "secret123"})
    assert r.status_code == 200

    # 重置
    r = client.post(
        f"/api/users/{uid}/reset-password",
        json={"password": "newpass456"},
        headers=admin_headers,
    )
    assert r.status_code == 200

    # 旧密码失效
    r = client.post("/api/auth/login", data={"username": "alice", "password": "secret123"})
    assert r.status_code == 401
    # 新密码可登录
    r = client.post("/api/auth/login", data={"username": "alice", "password": "newpass456"})
    assert r.status_code == 200


def test_delete_is_soft_deactivation(client, admin_headers):
    r = client.post("/api/users", json=_create_payload(), headers=admin_headers)
    uid = r.json()["id"]

    r = client.delete(f"/api/users/{uid}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # 仍可 GET（账户未真删）
    r = client.get(f"/api/users/{uid}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # 不能再登录
    r = client.post("/api/auth/login", data={"username": "alice", "password": "secret123"})
    assert r.status_code == 401


def test_admin_cannot_deactivate_self(client, admin_headers):
    # admin 在 fixture 里 username=admin，先找 id
    r = client.get("/api/users?role=ADMIN", headers=admin_headers)
    admin_id = r.json()["items"][0]["id"]

    r = client.delete(f"/api/users/{admin_id}", headers=admin_headers)
    assert r.status_code == 400
    assert "yourself" in r.json()["detail"]

    r = client.patch(
        f"/api/users/{admin_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_admin_cannot_demote_self(client, admin_headers):
    r = client.get("/api/users?role=ADMIN", headers=admin_headers)
    admin_id = r.json()["items"][0]["id"]

    r = client.patch(
        f"/api/users/{admin_id}",
        json={"role": "VIEWER"},
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "demote" in r.json()["detail"]


def test_viewer_cannot_access_users_router(client, admin_headers, viewer_headers):
    client.post("/api/users", json=_create_payload(), headers=admin_headers)
    r = client.get("/api/users", headers=viewer_headers)
    assert r.status_code == 403
    r = client.post("/api/users", json=_create_payload("bob"), headers=viewer_headers)
    assert r.status_code == 403


def test_create_with_invalid_username_returns_422(client, admin_headers):
    payload = _create_payload(username="ab")  # 短于 3
    r = client.post("/api/users", json=payload, headers=admin_headers)
    assert r.status_code == 422


def test_list_filters_by_role_and_is_active(client, admin_headers):
    client.post("/api/users", json=_create_payload("op1", "OPERATOR"), headers=admin_headers)
    client.post("/api/users", json=_create_payload("eng1", "METER_ENG"), headers=admin_headers)
    r = client.post("/api/users", json=_create_payload("vw1", "VIEWER"), headers=admin_headers)
    vw_id = r.json()["id"]
    client.delete(f"/api/users/{vw_id}", headers=admin_headers)

    assert client.get("/api/users?role=OPERATOR", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/users?role=ADMIN", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/users?is_active=false", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/users?is_active=true", headers=admin_headers).json()["total"] == 3

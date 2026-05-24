"""气源档案 router 集成测试。"""
from __future__ import annotations


def _sample_payload(code: str = "SRC-001") -> dict:
    return {
        "code": code,
        "name": "西气东输三线",
        "supplier": "中石油",
        "gas_type": "PIPELINE",
        "contract_no": "CNPC-2026-001",
        "contract_base_price": 2.8500,
        "daily_volume_plan_nm3": 1_200_000,
    }


def test_create_list_get_update_retire_full_flow(client, admin_headers):
    # CREATE
    r = client.post("/api/gas-sources", json=_sample_payload(), headers=admin_headers)
    assert r.status_code == 201, r.text
    created = r.json()
    src_id = created["id"]
    assert created["code"] == "SRC-001"
    assert created["status"] == "ACTIVE"

    # LIST
    r = client.get("/api/gas-sources", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == src_id

    # GET
    r = client.get(f"/api/gas-sources/{src_id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["supplier"] == "中石油"

    # PATCH
    r = client.patch(
        f"/api/gas-sources/{src_id}",
        json={"supplier": "中石油西部分公司"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["supplier"] == "中石油西部分公司"

    # RETIRE
    r = client.delete(f"/api/gas-sources/{src_id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "RETIRED"

    # LIST with status filter
    r = client.get("/api/gas-sources?status=ACTIVE", headers=admin_headers)
    assert r.json()["total"] == 0
    r = client.get("/api/gas-sources?status=RETIRED", headers=admin_headers)
    assert r.json()["total"] == 1


def test_viewer_cannot_create_gas_source(client, viewer_headers):
    r = client.post("/api/gas-sources", json=_sample_payload(), headers=viewer_headers)
    assert r.status_code == 403
    assert "not allowed" in r.json()["detail"]


def test_viewer_can_read_gas_sources(client, admin_headers, viewer_headers):
    client.post("/api/gas-sources", json=_sample_payload(), headers=admin_headers)
    r = client.get("/api/gas-sources", headers=viewer_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_duplicate_code_returns_409(client, admin_headers):
    client.post("/api/gas-sources", json=_sample_payload(), headers=admin_headers)
    r = client.post("/api/gas-sources", json=_sample_payload(), headers=admin_headers)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_get_nonexistent_returns_404(client, admin_headers):
    r = client.get("/api/gas-sources/9999", headers=admin_headers)
    assert r.status_code == 404


def test_create_with_invalid_code_returns_422(client, admin_headers):
    payload = _sample_payload(code="SRC-1")  # 不符合 SRC-NNN
    r = client.post("/api/gas-sources", json=payload, headers=admin_headers)
    assert r.status_code == 422

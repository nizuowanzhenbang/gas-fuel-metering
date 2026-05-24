"""计量站档案 router 集成测试。"""
from __future__ import annotations


def _src_payload(code: str = "SRC-001") -> dict:
    return {
        "code": code,
        "name": "西气东输",
        "supplier": "中石油",
        "gas_type": "PIPELINE",
    }


def _station_payload(code: str = "MS-01", source_id: int | None = None) -> dict:
    return {
        "code": code,
        "name": "1#计量站",
        "location": "厂区东北角",
        "source_id": source_id,
        "design_pressure_kpa": 3500.00,
        "design_flow_min_nm3h": 5000.0,
        "design_flow_max_nm3h": 50000.0,
    }


def test_create_station_with_gas_source_reference(client, admin_headers):
    src_id = client.post("/api/gas-sources", json=_src_payload(), headers=admin_headers).json()["id"]
    r = client.post(
        "/api/metering-stations",
        json=_station_payload(source_id=src_id),
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_id"] == src_id
    assert body["status"] == "RUNNING"


def test_reject_station_referencing_retired_source(client, admin_headers):
    src_id = client.post("/api/gas-sources", json=_src_payload(), headers=admin_headers).json()["id"]
    client.delete(f"/api/gas-sources/{src_id}", headers=admin_headers)  # → RETIRED

    r = client.post(
        "/api/metering-stations",
        json=_station_payload(source_id=src_id),
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "retired" in r.json()["detail"]


def test_reject_station_with_max_below_min(client, admin_headers):
    payload = _station_payload()
    payload["design_flow_min_nm3h"] = 50000.0
    payload["design_flow_max_nm3h"] = 10000.0
    r = client.post("/api/metering-stations", json=payload, headers=admin_headers)
    # Pydantic model_validator 会拒绝
    assert r.status_code == 422


def test_patch_keeps_flow_range_invariant(client, admin_headers):
    sid = client.post(
        "/api/metering-stations",
        json=_station_payload(),
        headers=admin_headers,
    ).json()["id"]

    # 把 max 改到比 min 还小 → 400
    r = client.patch(
        f"/api/metering-stations/{sid}",
        json={"design_flow_max_nm3h": 100.0},
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "design_flow_max" in r.json()["detail"]


def test_meter_eng_can_create_station(client, meter_eng_headers):
    r = client.post(
        "/api/metering-stations",
        json=_station_payload(),
        headers=meter_eng_headers,
    )
    assert r.status_code == 201

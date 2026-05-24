"""GC 档案 router 集成测试。"""
from __future__ import annotations


def _station_payload(code: str = "MS-01") -> dict:
    return {
        "code": code,
        "name": "1#计量站",
        "design_pressure_kpa": 3500.00,
        "design_flow_min_nm3h": 5000.0,
        "design_flow_max_nm3h": 50000.0,
    }


def _gc_payload(code: str = "GC-01", station_id: int | None = None) -> dict:
    return {
        "code": code,
        "model": "Daniel 700XA",
        "serial_no": "SN-2026-XYZ",
        "station_id": station_id,
    }


def test_create_gc_with_station_reference(client, admin_headers):
    sid = client.post(
        "/api/metering-stations", json=_station_payload(), headers=admin_headers
    ).json()["id"]
    r = client.post("/api/gc-analyzers", json=_gc_payload(station_id=sid), headers=admin_headers)
    assert r.status_code == 201, r.text
    assert r.json()["station_id"] == sid


def test_reject_gc_referencing_offline_station(client, admin_headers):
    sid = client.post(
        "/api/metering-stations", json=_station_payload(), headers=admin_headers
    ).json()["id"]
    client.delete(f"/api/metering-stations/{sid}", headers=admin_headers)  # → OFFLINE

    r = client.post(
        "/api/gc-analyzers", json=_gc_payload(station_id=sid), headers=admin_headers
    )
    assert r.status_code == 400
    assert "offline" in r.json()["detail"]


def test_filter_gc_by_station(client, admin_headers):
    s1 = client.post("/api/metering-stations", json=_station_payload("MS-01"), headers=admin_headers).json()["id"]
    s2 = client.post("/api/metering-stations", json=_station_payload("MS-02"), headers=admin_headers).json()["id"]
    client.post("/api/gc-analyzers", json=_gc_payload("GC-01", station_id=s1), headers=admin_headers)
    client.post("/api/gc-analyzers", json=_gc_payload("GC-02", station_id=s2), headers=admin_headers)
    client.post("/api/gc-analyzers", json=_gc_payload("GC-03", station_id=s2), headers=admin_headers)

    r = client.get(f"/api/gc-analyzers?station_id={s2}", headers=admin_headers)
    assert r.json()["total"] == 2

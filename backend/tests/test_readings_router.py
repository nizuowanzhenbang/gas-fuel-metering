"""时序读数 router 集成测试。验证算法回填与权限。"""
from __future__ import annotations

import math

from backend.utils.heating_value import Composition, compute_heating_value
from backend.utils.pressure_temp_compensation import (
    CompensationInput,
    compensate,
)


def _create_station(client, headers, code: str = "MS-01") -> int:
    return client.post(
        "/api/metering-stations",
        json={
            "code": code,
            "name": "1#计量站",
            "design_pressure_kpa": 3500.0,
            "design_flow_min_nm3h": 5000.0,
            "design_flow_max_nm3h": 50000.0,
        },
        headers=headers,
    ).json()["id"]


def _create_gc(client, headers, station_id: int | None = None, code: str = "GC-01") -> int:
    return client.post(
        "/api/gc-analyzers",
        json={
            "code": code,
            "model": "Daniel 700XA",
            "station_id": station_id,
        },
        headers=headers,
    ).json()["id"]


def test_post_metering_reading_normal_volume_matches_compensate(client, admin_headers):
    sid = _create_station(client, admin_headers)
    payload = {
        "station_id": sid,
        "ts": "2026-06-01T10:00:00+00:00",
        "actual_volume_rate_m3h": 1000.0,
        "gauge_pressure_kpa": 2000.0 - 101.325,  # 绝压 2 MPa 对齐 Z 表网格
        "temperature_c": 20.0,
        "accumulated_volume_nm3": 12_345_678.0,
    }
    r = client.post("/api/readings/metering", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()

    expected = compensate(
        CompensationInput(
            actual_volume_rate_m3h=1000.0,
            gauge_pressure_kpa=2000.0 - 101.325,
            temperature_c=20.0,
        )
    )
    # DB 字段 Numeric(12,3) / Numeric(10,2) → 3 / 2 位小数容差
    assert math.isclose(body["normal_volume_rate_nm3h"], expected.normal_volume_rate_nm3h, abs_tol=0.001)
    assert math.isclose(body["pressure_kpa"], expected.absolute_pressure_kpa, abs_tol=0.01)
    assert body["validity"] == "VALID"
    assert body["source"] == "PRIMARY"


def test_metering_rejects_offline_station(client, admin_headers):
    sid = _create_station(client, admin_headers)
    client.delete(f"/api/metering-stations/{sid}", headers=admin_headers)
    r = client.post(
        "/api/readings/metering",
        json={
            "station_id": sid,
            "ts": "2026-06-01T10:00:00+00:00",
            "actual_volume_rate_m3h": 100.0,
            "gauge_pressure_kpa": 1000.0,
            "temperature_c": 20.0,
            "accumulated_volume_nm3": 1.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "offline" in r.json()["detail"]


def test_metering_rejects_absolute_zero_temperature(client, admin_headers):
    sid = _create_station(client, admin_headers)
    r = client.post(
        "/api/readings/metering",
        json={
            "station_id": sid,
            "ts": "2026-06-01T10:00:00+00:00",
            "actual_volume_rate_m3h": 100.0,
            "gauge_pressure_kpa": 1000.0,
            "temperature_c": -300.0,
            "accumulated_volume_nm3": 1.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "temperature" in r.json()["detail"]


def test_list_metering_filters_by_station_and_validity(client, admin_headers):
    s1 = _create_station(client, admin_headers, "MS-01")
    s2 = _create_station(client, admin_headers, "MS-02")
    base = {
        "ts": "2026-06-01T10:00:00+00:00",
        "actual_volume_rate_m3h": 800.0,
        "gauge_pressure_kpa": 1500.0,
        "temperature_c": 25.0,
        "accumulated_volume_nm3": 100.0,
    }
    client.post("/api/readings/metering", json={**base, "station_id": s1}, headers=admin_headers)
    client.post(
        "/api/readings/metering",
        json={**base, "station_id": s2, "validity": "CALIBRATING"},
        headers=admin_headers,
    )
    client.post("/api/readings/metering", json={**base, "station_id": s2}, headers=admin_headers)

    assert client.get(f"/api/readings/metering?station_id={s2}", headers=admin_headers).json()["total"] == 2
    assert (
        client.get("/api/readings/metering?validity=CALIBRATING", headers=admin_headers).json()["total"]
        == 1
    )


def test_post_gc_reading_hhv_matches_compute_heating_value(client, admin_headers):
    sid = _create_station(client, admin_headers)
    gc_id = _create_gc(client, admin_headers, station_id=sid)
    payload = {
        "gc_id": gc_id,
        "station_id": sid,
        "ts": "2026-06-01T10:00:00+00:00",
        "ch4_pct": 96.0,
        "c2h6_pct": 2.0,
        "c3h8_pct": 0.5,
        "n2_pct": 0.5,
        "co2_pct": 1.0,
    }
    r = client.post("/api/readings/gc", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()

    expected = compute_heating_value(
        Composition(ch4_pct=96.0, c2h6_pct=2.0, c3h8_pct=0.5, n2_pct=0.5, co2_pct=1.0)
    )
    # DB 字段是 Numeric(8,3)，落库后保留 3 位小数 → 用 abs_tol 兜底
    assert math.isclose(body["hhv_mj_nm3"], expected.hhv_mj_nm3, abs_tol=0.001)
    assert math.isclose(body["wobbe_mj_nm3"], expected.wobbe_mj_nm3, abs_tol=0.001)


def test_gc_rejects_composition_sum_far_from_100(client, admin_headers):
    sid = _create_station(client, admin_headers)
    gc_id = _create_gc(client, admin_headers, station_id=sid)
    r = client.post(
        "/api/readings/gc",
        json={
            "gc_id": gc_id,
            "ts": "2026-06-01T10:00:00+00:00",
            "ch4_pct": 80.0,  # sum=80, 偏离 100 超过 ±1%
        },
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "deviates" in r.json()["detail"]


def test_viewer_cannot_post_metering_reading(client, admin_headers, viewer_headers):
    sid = _create_station(client, admin_headers)
    r = client.post(
        "/api/readings/metering",
        json={
            "station_id": sid,
            "ts": "2026-06-01T10:00:00+00:00",
            "actual_volume_rate_m3h": 100.0,
            "gauge_pressure_kpa": 1000.0,
            "temperature_c": 20.0,
            "accumulated_volume_nm3": 1.0,
        },
        headers=viewer_headers,
    )
    assert r.status_code == 403


def test_operator_can_post_metering_reading(client, admin_headers, operator_headers):
    sid = _create_station(client, admin_headers)
    r = client.post(
        "/api/readings/metering",
        json={
            "station_id": sid,
            "ts": "2026-06-01T10:00:00+00:00",
            "actual_volume_rate_m3h": 100.0,
            "gauge_pressure_kpa": 1000.0,
            "temperature_c": 20.0,
            "accumulated_volume_nm3": 1.0,
        },
        headers=operator_headers,
    )
    assert r.status_code == 201

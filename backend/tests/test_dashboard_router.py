"""实时大屏 router 集成测试。

覆盖：
- 空环境下 overview 全 0
- 多站点 + 24h 读数 → 总气量按 max-min 聚合
- GC 读数 → latest_hhv 出现
- 告警分级计数（INFO/WARN/CRITICAL）
- station_snapshots 按 code 排序，OFFLINE 站过滤
- VIEWER 也能读
"""
from __future__ import annotations


def _create_source(client, headers, code="SRC-001"):
    return client.post(
        "/api/gas-sources",
        json={"code": code, "name": code, "supplier": "中石油", "gas_type": "PIPELINE"},
        headers=headers,
    ).json()["id"]


def _create_station(client, headers, sid, code="MS-01", status_override=None):
    body = {
        "code": code,
        "name": code,
        "source_id": sid,
        "design_pressure_kpa": 3500.0,
        "design_flow_min_nm3h": 5000.0,
        "design_flow_max_nm3h": 50000.0,
    }
    r = client.post("/api/metering-stations", json=body, headers=headers)
    stid = r.json()["id"]
    if status_override:
        client.patch(f"/api/metering-stations/{stid}", json={"status": status_override}, headers=headers)
    return stid


def _create_gc(client, headers, stid, code="GC-01"):
    return client.post(
        "/api/gc-analyzers",
        json={"code": code, "model": "ABB NGC8200", "station_id": stid},
        headers=headers,
    ).json()["id"]


def _post_metering(client, headers, stid, ts, accum):
    client.post(
        "/api/readings/metering",
        json={
            "station_id": stid,
            "ts": ts,
            "actual_volume_rate_m3h": 1000.0,
            "gauge_pressure_kpa": 1500.0,
            "temperature_c": 20.0,
            "accumulated_volume_nm3": accum,
            "source": "PRIMARY",
            "validity": "VALID",
        },
        headers=headers,
    )


def _post_gc(client, headers, gcid, stid, ts):
    client.post(
        "/api/readings/gc",
        json={
            "gc_id": gcid,
            "station_id": stid,
            "ts": ts,
            "ch4_pct": 95.0,
            "c2h6_pct": 2.5,
            "c3h8_pct": 1.0,
            "ic4h10_pct": 0.2,
            "nc4h10_pct": 0.3,
            "n2_pct": 0.5,
            "co2_pct": 0.5,
            "others_pct": 0.0,
            "validity": "VALID",
        },
        headers=headers,
    )


def test_overview_empty(client, admin_headers):
    r = client.get("/api/dashboard/overview", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["active_sources"] == 0
    assert body["running_stations"] == 0
    assert body["online_gc"] == 0
    assert body["last_24h_volume_nm3"] == 0
    assert body["latest_hhv_mj_nm3"] is None
    assert body["open_alerts"] == {"info": 0, "warn": 0, "critical": 0}


def test_overview_aggregates_24h_volume_and_hhv(client, admin_headers):
    from datetime import datetime, timedelta, timezone

    sid = _create_source(client, admin_headers)
    st1 = _create_station(client, admin_headers, sid, "MS-01")
    st2 = _create_station(client, admin_headers, sid, "MS-02")
    gc = _create_gc(client, admin_headers, st1)

    now = datetime.now(timezone.utc)
    # 落在最近 24h 内
    a = (now - timedelta(hours=23)).isoformat()
    b = (now - timedelta(hours=1)).isoformat()
    _post_metering(client, admin_headers, st1, a, 1_000_000.0)
    _post_metering(client, admin_headers, st1, b, 1_500_000.0)  # +500k
    _post_metering(client, admin_headers, st2, a, 500_000.0)
    _post_metering(client, admin_headers, st2, b, 800_000.0)  # +300k
    _post_gc(client, admin_headers, gc, st1, b)

    r = client.get("/api/dashboard/overview", headers=admin_headers)
    body = r.json()
    assert body["active_sources"] == 1
    assert body["running_stations"] == 2
    assert body["online_gc"] == 1
    assert abs(body["last_24h_volume_nm3"] - 800_000.0) < 1.0
    assert body["latest_hhv_mj_nm3"] is not None and body["latest_hhv_mj_nm3"] > 30  # 典型管道气 HHV ~38


def test_overview_alert_level_counts(client, admin_headers):
    for level, category in [
        ("CRITICAL", "METER_OFFLINE"),
        ("CRITICAL", "GC_FAULT"),
        ("WARN", "PT_OUT_OF_RANGE"),
        ("INFO", "GC_CALIBRATION_DUE"),
    ]:
        client.post(
            "/api/alerts",
            json={"level": level, "category": category, "message": "x"},
            headers=admin_headers,
        )

    r = client.get("/api/dashboard/overview", headers=admin_headers)
    body = r.json()
    assert body["open_alerts"] == {"info": 1, "warn": 1, "critical": 2}


def test_station_snapshots_filters_offline_and_sorts(client, admin_headers):
    sid = _create_source(client, admin_headers)
    _create_station(client, admin_headers, sid, "MS-02")
    _create_station(client, admin_headers, sid, "MS-01")
    _create_station(client, admin_headers, sid, "MS-99", status_override="OFFLINE")

    r = client.get("/api/dashboard/stations", headers=admin_headers)
    body = r.json()
    assert [s["code"] for s in body] == ["MS-01", "MS-02"]


def test_viewer_can_read_dashboard(client, admin_headers, viewer_headers):
    _create_source(client, admin_headers)
    r = client.get("/api/dashboard/overview", headers=viewer_headers)
    assert r.status_code == 200
    r = client.get("/api/dashboard/stations", headers=viewer_headers)
    assert r.status_code == 200

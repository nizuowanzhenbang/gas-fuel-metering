"""对账 router 集成测试 —— 日对账 / 主备回路。

验证：
- 厂内累计聚合（完整 UTC 日的末值 - 首值）正确性
- 三档判定（PASS / WARN / FAIL）端到端
- RBAC：VIEWER 不可触发
- 数据缺失时返回 400（无站、无读数、主备缺一）
"""
from __future__ import annotations


def _create_source(client, headers, code: str = "SRC-001") -> int:
    return client.post(
        "/api/gas-sources",
        json={
            "code": code,
            "name": "西气东输三线",
            "supplier": "中石油",
            "gas_type": "PIPELINE",
        },
        headers=headers,
    ).json()["id"]


def _create_station(
    client, headers, source_id: int | None = None, code: str = "MS-01"
) -> int:
    return client.post(
        "/api/metering-stations",
        json={
            "code": code,
            "name": "1#计量站",
            "source_id": source_id,
            "design_pressure_kpa": 3500.0,
            "design_flow_min_nm3h": 5000.0,
            "design_flow_max_nm3h": 50000.0,
        },
        headers=headers,
    ).json()["id"]


def _post_reading(
    client,
    headers,
    *,
    station_id: int,
    ts: str,
    accumulated_volume_nm3: float,
    source: str = "PRIMARY",
    validity: str = "VALID",
) -> None:
    r = client.post(
        "/api/readings/metering",
        json={
            "station_id": station_id,
            "ts": ts,
            "actual_volume_rate_m3h": 1000.0,
            "gauge_pressure_kpa": 1500.0,
            "temperature_c": 20.0,
            "accumulated_volume_nm3": accumulated_volume_nm3,
            "source": source,
            "validity": validity,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text


# ------------------------------- 日对账 -------------------------------


def test_daily_pass_when_diff_within_tolerance(client, admin_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    _post_reading(
        client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
        accumulated_volume_nm3=1_000_000.0,
    )
    _post_reading(
        client, admin_headers, station_id=st, ts="2026-06-02T00:00:00+00:00",
        accumulated_volume_nm3=1_100_000.0,
    )

    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": sid,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 100_000.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "PASS"
    assert body["plant_volume_nm3"] == 100_000.0
    assert body["upstream_volume_nm3"] == 100_000.0
    assert body["relative_diff_pct"] == 0.0
    assert body["sample_count"] == 2
    assert body["source_code"] == "SRC-001"


def test_daily_warn_when_diff_between_tolerance_and_double(client, admin_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    _post_reading(
        client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
        accumulated_volume_nm3=0.0,
    )
    _post_reading(
        client, admin_headers, station_id=st, ts="2026-06-02T00:00:00+00:00",
        accumulated_volume_nm3=100_000.0,
    )
    # 上游 100700 → diff = -0.695%（>0.5%，<1.0%）→ WARN
    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": sid,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 100_700.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "WARN"
    assert body["relative_diff_pct"] < 0


def test_daily_fail_when_diff_exceeds_double_tolerance(client, admin_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    _post_reading(
        client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
        accumulated_volume_nm3=0.0,
    )
    _post_reading(
        client, admin_headers, station_id=st, ts="2026-06-02T00:00:00+00:00",
        accumulated_volume_nm3=100_000.0,
    )
    # 上游 102000 → diff ≈ -1.96% → FAIL（>1.0%）
    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": sid,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 102_000.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "FAIL"


def test_daily_aggregates_multiple_stations_of_same_source(client, admin_headers):
    sid = _create_source(client, admin_headers)
    s1 = _create_station(client, admin_headers, source_id=sid, code="MS-01")
    s2 = _create_station(client, admin_headers, source_id=sid, code="MS-02")
    for st, start, end in [(s1, 0.0, 60_000.0), (s2, 200.0, 40_200.0)]:
        _post_reading(
            client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
            accumulated_volume_nm3=start,
        )
        _post_reading(
            client, admin_headers, station_id=st, ts="2026-06-02T00:00:00+00:00",
            accumulated_volume_nm3=end,
        )

    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": sid,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 100_000.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    # 60000 (站1) + 40000 (站2) = 100000
    assert body["plant_volume_nm3"] == 100_000.0
    assert body["sample_count"] == 4
    assert body["verdict"] == "PASS"


def test_daily_ignores_other_dates_and_invalid_and_backup(client, admin_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    # 当日 PRIMARY VALID：1000 → 2000，目标值 1000
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
                  accumulated_volume_nm3=1000.0)
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-02T00:00:00+00:00",
                  accumulated_volume_nm3=2000.0)
    # 干扰：其他日期
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-02T01:00:00+00:00",
                  accumulated_volume_nm3=99_999.0)
    # 干扰：CALIBRATING
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T12:00:00+00:00",
                  accumulated_volume_nm3=88_888.0, validity="CALIBRATING")
    # 干扰：BACKUP
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T12:00:00+00:00",
                  accumulated_volume_nm3=77_777.0, source="BACKUP")

    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": sid,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 1000.0,
        },
        headers=admin_headers,
    )
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["plant_volume_nm3"] == 1000.0
    assert body["sample_count"] == 2


def test_daily_rejects_source_with_no_stations(client, admin_headers):
    sid = _create_source(client, admin_headers)
    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": sid,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 1.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "no metering stations" in r.json()["detail"]


def test_daily_rejects_when_no_valid_readings(client, admin_headers):
    sid = _create_source(client, admin_headers)
    _create_station(client, admin_headers, source_id=sid)
    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": sid,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 1.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "INSUFFICIENT_SAMPLES" in r.json()["detail"]["stations"][0]["issues"]


def test_daily_returns_404_for_unknown_source(client, admin_headers):
    r = client.post(
        "/api/reconciliation/daily",
        json={
            "source_id": 9999,
            "business_date": "2026-06-01",
            "upstream_volume_nm3": 1.0,
        },
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_daily_viewer_forbidden(client, admin_headers, viewer_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
                  accumulated_volume_nm3=0.0)
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-02T00:00:00+00:00",
                  accumulated_volume_nm3=100.0)
    r = client.post(
        "/api/reconciliation/daily",
        json={"source_id": sid, "business_date": "2026-06-01", "upstream_volume_nm3": 100.0},
        headers=viewer_headers,
    )
    assert r.status_code == 403


# ------------------------------- 主备回路 -------------------------------


def test_dual_loop_pass_when_primary_matches_backup(client, admin_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
                  accumulated_volume_nm3=0.0, source="PRIMARY")
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T23:00:00+00:00",
                  accumulated_volume_nm3=1000.0, source="PRIMARY")
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
                  accumulated_volume_nm3=500.0, source="BACKUP")
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T23:00:00+00:00",
                  accumulated_volume_nm3=1500.0, source="BACKUP")

    r = client.post(
        "/api/reconciliation/dual-loop",
        json={"station_id": st, "business_date": "2026-06-01"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "PASS"
    assert body["primary_volume_nm3"] == 1000.0
    assert body["backup_volume_nm3"] == 1000.0
    assert body["primary_sample_count"] == 2
    assert body["backup_sample_count"] == 2
    assert body["station_code"] == "MS-01"


def test_dual_loop_fail_when_diff_exceeds_double_tolerance(client, admin_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    # primary 1000, backup 1015 → mean=1007.5, diff=15 → 1.49% > 0.6%
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
                  accumulated_volume_nm3=0.0, source="PRIMARY")
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T23:00:00+00:00",
                  accumulated_volume_nm3=1000.0, source="PRIMARY")
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
                  accumulated_volume_nm3=0.0, source="BACKUP")
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T23:00:00+00:00",
                  accumulated_volume_nm3=1015.0, source="BACKUP")

    r = client.post(
        "/api/reconciliation/dual-loop",
        json={"station_id": st, "business_date": "2026-06-01"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "FAIL"


def test_dual_loop_rejects_when_backup_has_no_readings(client, admin_headers):
    sid = _create_source(client, admin_headers)
    st = _create_station(client, admin_headers, source_id=sid)
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T00:00:00+00:00",
                  accumulated_volume_nm3=0.0, source="PRIMARY")
    _post_reading(client, admin_headers, station_id=st, ts="2026-06-01T23:00:00+00:00",
                  accumulated_volume_nm3=1000.0, source="PRIMARY")

    r = client.post(
        "/api/reconciliation/dual-loop",
        json={"station_id": st, "business_date": "2026-06-01"},
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "INSUFFICIENT_SAMPLES" in r.json()["detail"]["stations"][1]["issues"]


def test_dual_loop_returns_404_for_unknown_station(client, admin_headers):
    r = client.post(
        "/api/reconciliation/dual-loop",
        json={"station_id": 9999, "business_date": "2026-06-01"},
        headers=admin_headers,
    )
    assert r.status_code == 404

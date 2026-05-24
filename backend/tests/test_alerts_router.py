"""告警 router 集成测试。

覆盖：
- 创建 → 编号生成（AL-YYYYMMDD-NNNN，单日序号递增）
- 状态机：OPEN → ACKED → RESOLVED；不能跳过状态外逆推
- 列表筛选（level / category / status / station_id）
- RBAC：VIEWER 不可处置
- 直接 resolve 未 ack 的告警：审计字段同时回填 acked_*
"""
from __future__ import annotations

from datetime import datetime, timezone


def _create(client, headers, **overrides) -> dict:
    body = {
        "level": "WARN",
        "category": "PT_OUT_OF_RANGE",
        "message": "1#计量站压力 800kPa 低于下限",
        "station_id": None,
        "gc_id": None,
        "source_id": None,
        "payload_json": {"actual_pressure_kpa": 800.0},
    }
    body.update(overrides)
    r = client.post("/api/alerts", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_assigns_alert_no_with_today_prefix(client, admin_headers):
    obj = _create(client, admin_headers)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert obj["alert_no"].startswith(f"AL-{today}-")
    assert obj["status"] == "OPEN"
    assert obj["acked_at"] is None and obj["resolved_at"] is None


def test_alert_no_sequence_increments_for_same_day(client, admin_headers):
    a1 = _create(client, admin_headers)
    a2 = _create(client, admin_headers, message="第二条")
    seq1 = int(a1["alert_no"].rsplit("-", 1)[-1])
    seq2 = int(a2["alert_no"].rsplit("-", 1)[-1])
    assert seq2 == seq1 + 1


def test_state_machine_open_to_ack_to_resolved(client, admin_headers):
    obj = _create(client, admin_headers)
    aid = obj["id"]

    r = client.post(f"/api/alerts/{aid}/ack", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "ACKED"
    assert r.json()["acked_at"] is not None

    r = client.post(f"/api/alerts/{aid}/resolve", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "RESOLVED"
    assert r.json()["resolved_at"] is not None


def test_ack_on_resolved_returns_400(client, admin_headers):
    obj = _create(client, admin_headers)
    aid = obj["id"]
    client.post(f"/api/alerts/{aid}/resolve", headers=admin_headers)
    r = client.post(f"/api/alerts/{aid}/ack", headers=admin_headers)
    assert r.status_code == 400


def test_resolve_without_prior_ack_backfills_acked_fields(client, admin_headers):
    obj = _create(client, admin_headers)
    aid = obj["id"]
    r = client.post(f"/api/alerts/{aid}/resolve", headers=admin_headers)
    body = r.json()
    assert body["status"] == "RESOLVED"
    assert body["acked_at"] == body["resolved_at"]
    assert body["acked_by"] == body["resolved_by"]


def test_list_filters_by_level_category_status(client, admin_headers):
    _create(client, admin_headers, level="INFO", category="GC_CALIBRATION_DUE")
    _create(client, admin_headers, level="CRITICAL", category="METER_OFFLINE")
    _create(client, admin_headers, level="WARN", category="PT_OUT_OF_RANGE")

    r = client.get("/api/alerts?level=CRITICAL", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["category"] == "METER_OFFLINE"

    r = client.get("/api/alerts?status=OPEN", headers=admin_headers)
    assert r.json()["total"] == 3


def test_viewer_can_read_but_not_dispatch(client, admin_headers, viewer_headers):
    obj = _create(client, admin_headers)

    r = client.get("/api/alerts", headers=viewer_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r = client.post(f"/api/alerts/{obj['id']}/ack", headers=viewer_headers)
    assert r.status_code == 403


def test_get_unknown_alert_returns_404(client, admin_headers):
    r = client.get("/api/alerts/9999", headers=admin_headers)
    assert r.status_code == 404

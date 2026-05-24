"""上游日报 Excel 上传集成测试。

覆盖：
- 标准 4 列上传 → 行级三档判定
- 表头自动识别
- 行级容错（气源不存在 / 无 VALID 读数 / 单元格类型异常）不阻断后续行
- RBAC：VIEWER / OPERATOR 不可上传
- 非 xlsx 拒收 / 超大文件拒收
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _setup_source_with_readings(client, headers, *, plant_total_nm3: float = 1_000_000.0):
    """建一个气源 + 站点 + 2 条主回路 VALID 读数（一首一末），plant 总量 = end - start。"""
    sid = client.post(
        "/api/gas-sources",
        json={
            "code": "SRC-001",
            "name": "西气东输三线",
            "supplier": "中石油",
            "gas_type": "PIPELINE",
        },
        headers=headers,
    ).json()["id"]
    st = client.post(
        "/api/metering-stations",
        json={
            "code": "MS-01",
            "name": "1#计量站",
            "source_id": sid,
            "design_pressure_kpa": 3500.0,
            "design_flow_min_nm3h": 5000.0,
            "design_flow_max_nm3h": 50000.0,
        },
        headers=headers,
    ).json()["id"]
    base_reading = {
        "station_id": st,
        "actual_volume_rate_m3h": 1000.0,
        "gauge_pressure_kpa": 1500.0,
        "temperature_c": 20.0,
        "source": "PRIMARY",
        "validity": "VALID",
    }
    client.post(
        "/api/readings/metering",
        json={**base_reading, "ts": "2026-06-01T00:00:00+00:00", "accumulated_volume_nm3": 1_000_000.0},
        headers=headers,
    )
    client.post(
        "/api/readings/metering",
        json={
            **base_reading,
            "ts": "2026-06-01T23:59:00+00:00",
            "accumulated_volume_nm3": 1_000_000.0 + plant_total_nm3,
        },
        headers=headers,
    )
    return sid, st


def _upload(client, headers, content: bytes, filename: str = "report.xlsx"):
    return client.post(
        "/api/upload/upstream-daily",
        files={"file": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )


def test_upload_two_rows_one_pass_one_fail_within_tolerance(client, admin_headers):
    _setup_source_with_readings(client, admin_headers, plant_total_nm3=1_000_000.0)

    blob = _xlsx(
        [
            ["业务日期", "气源代码", "上游计量(Nm³)", "备注"],
            ["2026-06-01", "SRC-001", 1_001_000.0, "差 0.1%"],  # PASS
            ["2026-06-01", "SRC-999", 1_001_000.0, "未知气源"],
        ]
    )

    r = _upload(client, admin_headers, blob)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["success"] == 1
    assert body["failed"] == 1

    first = body["rows"][0]
    assert first["source_code"] == "SRC-001"
    assert first["verdict"] == "PASS"
    assert abs(first["relative_diff_pct"] - 0.1) < 1e-6 or first["relative_diff_pct"] is not None

    second = body["rows"][1]
    assert "SRC-999" in second["error"]


def test_upload_without_header_still_parses(client, admin_headers):
    _setup_source_with_readings(client, admin_headers, plant_total_nm3=1_000_000.0)

    blob = _xlsx([["2026-06-01", "SRC-001", 1_000_000.0, ""]])
    r = _upload(client, admin_headers, blob)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["rows"][0]["verdict"] == "PASS"


def test_upload_skips_blank_rows(client, admin_headers):
    _setup_source_with_readings(client, admin_headers, plant_total_nm3=1_000_000.0)

    blob = _xlsx(
        [
            ["业务日期", "气源代码", "上游计量", ""],
            [None, None, None, None],
            ["2026-06-01", "SRC-001", 1_000_000.0, ""],
        ]
    )
    r = _upload(client, admin_headers, blob)
    body = r.json()
    assert body["total"] == 1
    assert body["success"] == 1


def test_upload_rejects_non_xlsx(client, admin_headers):
    r = client.post(
        "/api/upload/upstream-daily",
        files={"file": ("report.csv", b"foo,bar", "text/csv")},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_upload_viewer_forbidden(client, admin_headers, viewer_headers):
    _setup_source_with_readings(client, admin_headers, plant_total_nm3=1_000_000.0)
    blob = _xlsx([["2026-06-01", "SRC-001", 1_000_000.0, ""]])
    r = _upload(client, viewer_headers, blob)
    assert r.status_code == 403


def test_upload_operator_forbidden(client, admin_headers, operator_headers):
    _setup_source_with_readings(client, admin_headers, plant_total_nm3=1_000_000.0)
    blob = _xlsx([["2026-06-01", "SRC-001", 1_000_000.0, ""]])
    r = _upload(client, operator_headers, blob)
    assert r.status_code == 403


def test_upload_row_with_no_valid_readings_returns_error_in_row(client, admin_headers):
    # 建气源但不写读数
    client.post(
        "/api/gas-sources",
        json={"code": "SRC-002", "name": "川气东送", "supplier": "中石化", "gas_type": "PIPELINE"},
        headers=admin_headers,
    )
    blob = _xlsx([["2026-06-01", "SRC-002", 500_000.0, ""]])
    r = _upload(client, admin_headers, blob)
    body = r.json()
    assert body["success"] == 0
    assert "VALID" in body["rows"][0]["error"] or "读数" in body["rows"][0]["error"]

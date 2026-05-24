"""上游日报 Excel 批量导入并触发日对账。

输入文件约定（中石油 / 中石化 / 中海油 通用列序）：
| 业务日期 | 气源代码 | 上游计量(Nm³) | 备注(可选) |
| -------- | -------- | ------------- | ---------- |

第 1 行允许为表头（无论中英文），第 2 行起为数据。空行跳过。

行级处理流程：
1. 解析 4 列 → 业务日期 / 气源 code / 上游体积 / 备注
2. 按 code 找 GasSource；查不到 → 行错误
3. 聚合该气源当日厂内主回路体积（与 reconciliation.daily 一致逻辑）
4. 调 utils.reconciliation.reconcile_daily
5. 失败原因捕获到行错误，不阻断后续行

返回报文：summary + per-row 结果（成功 / 失败原因）。
权限：ACCOUNTANT / ADMIN（结算口径，运行口径不开放）。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, Role, require_roles
from ..models.gas_sources import GasSource
from ..models.metering_readings import MeteringReading, MeteringSource, Validity
from ..models.metering_stations import MeteringStation
from ..utils.reconciliation import reconcile_daily

router = APIRouter(prefix="/api/upload", tags=["upload"])

require_uploader = require_roles(Role.ADMIN, Role.ACCOUNTANT)

MAX_ROWS = 1000  # 防爆量
MAX_BYTES = 5 * 1024 * 1024  # 5 MB


class UploadRowResult(BaseModel):
    row_index: int  # 1-based，便于操作员对应 Excel 行号
    business_date: date | None = None
    source_code: str | None = None
    plant_volume_nm3: float | None = None
    upstream_volume_nm3: float | None = None
    relative_diff_pct: float | None = None
    verdict: str | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    total: int
    success: int
    failed: int
    rows: list[UploadRowResult]


def _date_window_utc(business_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(business_date, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _aggregate_plant_volume(db, source_id: int, business_date: date) -> tuple[float, int]:
    start, end = _date_window_utc(business_date)
    stations = db.scalars(
        select(MeteringStation).where(MeteringStation.source_id == source_id)
    ).all()
    plant_total = 0.0
    sample_total = 0
    for st in stations:
        row = db.execute(
            select(
                func.max(MeteringReading.accumulated_volume_nm3),
                func.min(MeteringReading.accumulated_volume_nm3),
                func.count(MeteringReading.id),
            ).where(
                MeteringReading.station_id == st.id,
                MeteringReading.source == MeteringSource.PRIMARY,
                MeteringReading.validity == Validity.VALID,
                MeteringReading.ts >= start,
                MeteringReading.ts < end,
            )
        ).one()
        max_v, min_v, cnt = row
        if cnt and max_v is not None and min_v is not None:
            plant_total += float(max_v) - float(min_v)
            sample_total += int(cnt)
    return plant_total, sample_total


def _coerce_business_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip()[:10])
    raise ValueError(f"无法识别的业务日期：{value!r}")


def _coerce_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.replace(",", "").strip())
    raise ValueError(f"无法识别的数字：{value!r}")


def _is_header_row(cells: tuple) -> bool:
    """首行检测：4 个单元格里只要有任一为字符串且不能解析成日期，就视为表头。"""
    first = cells[0]
    if isinstance(first, (date, datetime)):
        return False
    if isinstance(first, str):
        try:
            _coerce_business_date(first)
            return False
        except ValueError:
            return True
    return False


@router.post("/upstream-daily", response_model=UploadResponse)
async def upload_upstream_daily(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_uploader)],
    file: UploadFile = File(...),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件必须为 .xlsx / .xlsm",
        )

    blob = await file.read()
    if len(blob) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件超过 {MAX_BYTES // 1024 // 1024} MB 限制",
        )

    try:
        wb = load_workbook(BytesIO(blob), read_only=True, data_only=True)
    except (InvalidFileException, KeyError) as exc:  # KeyError 出自 zip 解析失败
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Excel 解析失败：{exc}") from exc

    ws = wb.active
    if ws is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="工作簿为空")

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="工作表为空")

    # 表头检测：丢掉第 1 行，但保留原 Excel 行号
    has_header = _is_header_row(rows[0])
    data_start = 2 if has_header else 1
    data_rows = rows[1:] if has_header else rows

    if len(data_rows) > MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"行数超过 {MAX_ROWS} 上限，请分批上传",
        )

    results: list[UploadRowResult] = []
    success = 0
    for idx, row in enumerate(data_rows, start=data_start):
        # 跳过空行
        if row is None or all(cell is None or cell == "" for cell in row):
            continue
        result = UploadRowResult(row_index=idx)
        try:
            if len(row) < 3:
                raise ValueError("列数不足 3 列（业务日期 / 气源代码 / 上游计量）")
            bdate = _coerce_business_date(row[0])
            code = str(row[1]).strip().upper()
            upstream = _coerce_float(row[2])

            result.business_date = bdate
            result.source_code = code
            result.upstream_volume_nm3 = upstream

            source = db.scalar(select(GasSource).where(GasSource.code == code))
            if not source:
                raise ValueError(f"气源代码 {code} 不存在")

            plant_total, sample_count = _aggregate_plant_volume(db, source.id, bdate)
            if sample_count == 0:
                raise ValueError(f"{bdate.isoformat()} 该气源下无 VALID 主回路读数")

            verdict = reconcile_daily(plant_total, upstream)
            result.plant_volume_nm3 = verdict.plant_volume_nm3
            result.relative_diff_pct = verdict.relative_diff_pct
            result.verdict = verdict.verdict.value
            success += 1
        except Exception as exc:  # noqa: BLE001  按行容错
            result.error = str(exc)
        results.append(result)

    return UploadResponse(
        total=len(results),
        success=success,
        failed=len(results) - success,
        rows=results,
    )

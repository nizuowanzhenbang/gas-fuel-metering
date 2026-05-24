"""对账路由 —— 手动触发日对账与主备回路对账。

业务约定（CLAUDE.md / utils.reconciliation）：
- **日对账**：厂内 vs 上游日报，容差 0.5%（基准 = 上游）
- **主备回路**：同一计量站的主备流量计，容差 0.3%（基准 = 两者平均）

厂内日累计聚合规则：取气源下所有计量站 **主用回路** 的 VALID 读数，按
`max(accumulated_volume_nm3) - min(accumulated_volume_nm3)` 逐站求差再求和。
该方法不依赖采样间隔（区别于"对瞬时流率积分"），只要每站当日至少 2 条读数即可。

权限：触发 = ADMIN / METER_ENG / ACCOUNTANT，仅读视图待 dashboard router 接入时再开。
月结算单完整生命周期划入 v0.2，本路由不入库 SettlementRecord。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, Role, require_roles
from ..models.gas_sources import GasSource
from ..models.metering_readings import MeteringReading, MeteringSource, Validity
from ..models.metering_stations import MeteringStation
from ..schemas.reconciliation import (
    DailyReconciliationRequest,
    DailyReconciliationResponse,
    DualLoopReconciliationRequest,
    DualLoopReconciliationResponse,
)
from ..utils.reconciliation import reconcile_daily, reconcile_dual_loop

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])

require_reconciler = require_roles(Role.ADMIN, Role.METER_ENG, Role.ACCOUNTANT)


def _date_window_utc(business_date: date) -> tuple[datetime, datetime]:
    """按 UTC 把业务日期展开为 [00:00, 次日 00:00) 闭开区间。"""
    start = datetime.combine(business_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _aggregate_station_volume(
    db,
    *,
    station_id: int,
    metering_source: MeteringSource,
    start: datetime,
    end: datetime,
) -> tuple[float, int]:
    """按 (max - min) 聚合单站单日体积。返回 (体积 Nm³, 样本数)。"""
    row = db.execute(
        select(
            func.max(MeteringReading.accumulated_volume_nm3),
            func.min(MeteringReading.accumulated_volume_nm3),
            func.count(MeteringReading.id),
        ).where(
            MeteringReading.station_id == station_id,
            MeteringReading.source == metering_source,
            MeteringReading.validity == Validity.VALID,
            MeteringReading.ts >= start,
            MeteringReading.ts < end,
        )
    ).one()
    max_v, min_v, cnt = row
    if cnt == 0 or max_v is None or min_v is None:
        return 0.0, 0
    return float(max_v) - float(min_v), int(cnt)


@router.post("/daily", response_model=DailyReconciliationResponse)
def reconcile_daily_endpoint(
    payload: DailyReconciliationRequest,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_reconciler)],
) -> DailyReconciliationResponse:
    source = db.get(GasSource, payload.source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gas source not found")

    stations = db.scalars(
        select(MeteringStation).where(MeteringStation.source_id == payload.source_id)
    ).all()
    if not stations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="gas source has no metering stations bound; nothing to reconcile",
        )

    start, end = _date_window_utc(payload.business_date)
    plant_total = 0.0
    sample_total = 0
    for st in stations:
        vol, cnt = _aggregate_station_volume(
            db,
            station_id=st.id,
            metering_source=MeteringSource.PRIMARY,
            start=start,
            end=end,
        )
        plant_total += vol
        sample_total += cnt

    if sample_total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"no valid primary readings for source on {payload.business_date.isoformat()}",
        )

    try:
        result = reconcile_daily(plant_total, payload.upstream_volume_nm3)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return DailyReconciliationResponse(
        source_id=source.id,
        source_code=source.code,
        business_date=payload.business_date,
        plant_volume_nm3=result.plant_volume_nm3,
        upstream_volume_nm3=result.upstream_volume_nm3,
        absolute_diff_nm3=result.absolute_diff_nm3,
        relative_diff_pct=result.relative_diff_pct,
        tolerance_pct=result.tolerance_pct,
        verdict=result.verdict,
        reason=result.reason,
        sample_count=sample_total,
    )


@router.post("/dual-loop", response_model=DualLoopReconciliationResponse)
def reconcile_dual_loop_endpoint(
    payload: DualLoopReconciliationRequest,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_reconciler)],
) -> DualLoopReconciliationResponse:
    station = db.get(MeteringStation, payload.station_id)
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="metering station not found")

    start, end = _date_window_utc(payload.business_date)
    primary_vol, primary_cnt = _aggregate_station_volume(
        db,
        station_id=station.id,
        metering_source=MeteringSource.PRIMARY,
        start=start,
        end=end,
    )
    backup_vol, backup_cnt = _aggregate_station_volume(
        db,
        station_id=station.id,
        metering_source=MeteringSource.BACKUP,
        start=start,
        end=end,
    )

    if primary_cnt == 0 or backup_cnt == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"dual-loop reconciliation requires both primary and backup readings "
                f"(primary={primary_cnt}, backup={backup_cnt})"
            ),
        )

    try:
        result = reconcile_dual_loop(primary_vol, backup_vol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return DualLoopReconciliationResponse(
        station_id=station.id,
        station_code=station.code,
        business_date=payload.business_date,
        primary_volume_nm3=result.primary_volume_nm3,
        backup_volume_nm3=result.backup_volume_nm3,
        absolute_diff_nm3=result.absolute_diff_nm3,
        relative_diff_pct=result.relative_diff_pct,
        tolerance_pct=result.tolerance_pct,
        verdict=result.verdict,
        reason=result.reason,
        primary_sample_count=primary_cnt,
        backup_sample_count=backup_cnt,
    )

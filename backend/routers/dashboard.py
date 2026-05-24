"""实时大屏聚合接口（只读，全角色可访问）。

设计目标：用 **最少的查询次数** 把"概览页"和"按站详情"撑起来，
不在这里做时序分页，时序由 readings router 提供。

输出语义：
- /overview：站点数 / GC 数 / 进 24h 总气量（Nm³）/ 当前最新 HHV / 24h 内告警分级计数 / 当日对账状态
- /stations：每个非 OFFLINE 站点的最新瞬时流率 + 累计 + 最近 HHV + 最近告警 level
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, get_current_user
from ..models.alerts import Alert, AlertLevel, AlertStatus
from ..models.gas_sources import GasSource, GasSourceStatus
from ..models.gc_analyzers import GCAnalyzer, GCStatus
from ..models.gc_readings import GCReading
from ..models.metering_readings import MeteringReading, MeteringSource, Validity
from ..models.metering_stations import MeteringStation, StationStatus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AlertLevelCount(BaseModel):
    info: int = 0
    warn: int = 0
    critical: int = 0


class OverviewResponse(BaseModel):
    active_sources: int
    running_stations: int
    online_gc: int
    last_24h_volume_nm3: float
    latest_hhv_mj_nm3: float | None
    open_alerts: AlertLevelCount
    verification_due_30d: int  # 30 天内到期的计量器具数量


class StationSnapshot(BaseModel):
    station_id: int
    code: str
    name: str
    status: StationStatus
    source_code: str | None
    latest_ts: datetime | None
    latest_normal_volume_rate_nm3h: float | None
    latest_pressure_kpa: float | None
    latest_temperature_c: float | None
    accumulated_volume_nm3: float | None
    latest_hhv_mj_nm3: float | None
    last_alert_level: AlertLevel | None


@router.get("/overview", response_model=OverviewResponse)
def overview(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> OverviewResponse:
    now = _now()
    since = now - timedelta(hours=24)

    active_sources = db.scalar(
        select(func.count()).select_from(GasSource).where(GasSource.status == GasSourceStatus.ACTIVE)
    ) or 0
    running_stations = db.scalar(
        select(func.count()).select_from(MeteringStation).where(MeteringStation.status == StationStatus.RUNNING)
    ) or 0
    online_gc = db.scalar(
        select(func.count()).select_from(GCAnalyzer).where(GCAnalyzer.status == GCStatus.RUNNING)
    ) or 0

    # 24h 总气量 = sum over stations of (max - min) for VALID PRIMARY 读数
    stations = db.scalars(select(MeteringStation.id)).all()
    total_24h = 0.0
    for sid in stations:
        row = db.execute(
            select(
                func.max(MeteringReading.accumulated_volume_nm3),
                func.min(MeteringReading.accumulated_volume_nm3),
            ).where(
                MeteringReading.station_id == sid,
                MeteringReading.source == MeteringSource.PRIMARY,
                MeteringReading.validity == Validity.VALID,
                MeteringReading.ts >= since,
            )
        ).one()
        mx, mn = row
        if mx is not None and mn is not None:
            total_24h += float(mx) - float(mn)

    latest_hhv = db.scalar(
        select(GCReading.hhv_mj_nm3)
        .where(GCReading.validity == Validity.VALID)
        .order_by(GCReading.ts.desc())
        .limit(1)
    )

    open_alerts = AlertLevelCount()
    rows = db.execute(
        select(Alert.level, func.count()).where(Alert.status == AlertStatus.OPEN).group_by(Alert.level)
    ).all()
    for level, cnt in rows:
        if level == AlertLevel.INFO.value:
            open_alerts.info = int(cnt)
        elif level == AlertLevel.WARN.value:
            open_alerts.warn = int(cnt)
        elif level == AlertLevel.CRITICAL.value:
            open_alerts.critical = int(cnt)

    cutoff = now + timedelta(days=30)
    verification_due = db.scalar(
        select(func.count())
        .select_from(MeteringStation)
        .where(
            MeteringStation.verified_until.is_not(None),
            MeteringStation.verified_until <= cutoff,
            MeteringStation.verified_until >= now,
        )
    ) or 0

    return OverviewResponse(
        active_sources=int(active_sources),
        running_stations=int(running_stations),
        online_gc=int(online_gc),
        last_24h_volume_nm3=round(total_24h, 3),
        latest_hhv_mj_nm3=float(latest_hhv) if latest_hhv is not None else None,
        open_alerts=open_alerts,
        verification_due_30d=int(verification_due),
    )


@router.get("/stations", response_model=list[StationSnapshot])
def station_snapshots(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[StationSnapshot]:
    stations = db.scalars(
        select(MeteringStation).where(MeteringStation.status != StationStatus.OFFLINE).order_by(MeteringStation.code)
    ).all()

    snapshots: list[StationSnapshot] = []
    for st in stations:
        source_code = None
        if st.source_id:
            source_code = db.scalar(select(GasSource.code).where(GasSource.id == st.source_id))

        latest = db.execute(
            select(MeteringReading).where(
                MeteringReading.station_id == st.id,
                MeteringReading.source == MeteringSource.PRIMARY,
            ).order_by(MeteringReading.ts.desc()).limit(1)
        ).scalar_one_or_none()

        latest_hhv = db.scalar(
            select(GCReading.hhv_mj_nm3)
            .where(GCReading.station_id == st.id, GCReading.validity == Validity.VALID)
            .order_by(GCReading.ts.desc())
            .limit(1)
        )

        last_alert_level = db.scalar(
            select(Alert.level)
            .where(Alert.station_id == st.id, Alert.status == AlertStatus.OPEN)
            .order_by(Alert.opened_at.desc())
            .limit(1)
        )

        snapshots.append(
            StationSnapshot(
                station_id=st.id,
                code=st.code,
                name=st.name,
                status=StationStatus(st.status),
                source_code=source_code,
                latest_ts=latest.ts if latest else None,
                latest_normal_volume_rate_nm3h=float(latest.normal_volume_rate_nm3h) if latest else None,
                latest_pressure_kpa=float(latest.pressure_kpa) if latest else None,
                latest_temperature_c=float(latest.temperature_c) if latest else None,
                accumulated_volume_nm3=float(latest.accumulated_volume_nm3) if latest else None,
                latest_hhv_mj_nm3=float(latest_hhv) if latest_hhv is not None else None,
                last_alert_level=AlertLevel(last_alert_level) if last_alert_level else None,
            )
        )
    return snapshots

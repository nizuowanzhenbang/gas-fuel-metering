"""时序读数路由 —— 计量分钟级读数 + GC 组分读数。

POST：接收原始观测量，后端自动调 utils 算法补全（温压补偿 / 热值），写入。
GET：按站 / GC / 时间窗 / 有效性筛选，分页返回。
权限：写 = ADMIN / METER_ENG / OPERATOR，读 = 全部已登录角色。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, get_current_user, require_operator
from ..models.gc_analyzers import GCAnalyzer, GCStatus
from ..models.gc_readings import GCReading
from ..models.metering_readings import MeteringReading, Validity
from ..models.metering_stations import MeteringStation, StationStatus
from ..schemas.common import PagedResult
from ..schemas.readings import (
    GCReadingCreate,
    GCReadingRead,
    MeteringReadingCreate,
    MeteringReadingRead,
)
from ..utils.heating_value import Composition, compute_heating_value
from ..utils.pressure_temp_compensation import (
    DEFAULT_ATMOSPHERIC_KPA,
    CompensationInput,
    compensate,
)

router = APIRouter(prefix="/api/readings", tags=["readings"])


# ------------------------------- 计量读数 -------------------------------


@router.post(
    "/metering",
    response_model=MeteringReadingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_metering_reading(
    payload: MeteringReadingCreate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_operator)],
) -> MeteringReadingRead:
    station = db.get(MeteringStation, payload.station_id)
    if not station:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="station not found")
    if station.status == StationStatus.OFFLINE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="station is offline; readings rejected",
        )

    try:
        result = compensate(
            CompensationInput(
                actual_volume_rate_m3h=payload.actual_volume_rate_m3h,
                gauge_pressure_kpa=payload.gauge_pressure_kpa,
                temperature_c=payload.temperature_c,
                atmospheric_kpa=payload.atmospheric_kpa or DEFAULT_ATMOSPHERIC_KPA,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    row = MeteringReading(
        station_id=payload.station_id,
        ts=payload.ts,
        actual_volume_rate_m3h=payload.actual_volume_rate_m3h,
        normal_volume_rate_nm3h=result.normal_volume_rate_nm3h,
        pressure_kpa=result.absolute_pressure_kpa,
        temperature_c=payload.temperature_c,
        accumulated_volume_nm3=payload.accumulated_volume_nm3,
        validity=payload.validity,
        source=payload.source,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return MeteringReadingRead.model_validate(row)


@router.get("/metering", response_model=PagedResult[MeteringReadingRead])
def list_metering_readings(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
    station_id: int | None = Query(None),
    validity: Validity | None = Query(None),
    ts_from: datetime | None = Query(None),
    ts_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
) -> PagedResult[MeteringReadingRead]:
    stmt = select(MeteringReading)
    count_stmt = select(func.count()).select_from(MeteringReading)
    for clause in _build_metering_filters(station_id, validity, ts_from, ts_to):
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(MeteringReading.ts.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return PagedResult[MeteringReadingRead](
        total=total,
        page=page,
        size=size,
        items=[MeteringReadingRead.model_validate(r) for r in rows],
    )


def _build_metering_filters(
    station_id: int | None,
    validity: Validity | None,
    ts_from: datetime | None,
    ts_to: datetime | None,
):
    if station_id is not None:
        yield MeteringReading.station_id == station_id
    if validity is not None:
        yield MeteringReading.validity == validity
    if ts_from is not None:
        yield MeteringReading.ts >= ts_from
    if ts_to is not None:
        yield MeteringReading.ts <= ts_to


# ------------------------------- GC 读数 -------------------------------


@router.post(
    "/gc",
    response_model=GCReadingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_gc_reading(
    payload: GCReadingCreate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_operator)],
) -> GCReadingRead:
    gc = db.get(GCAnalyzer, payload.gc_id)
    if not gc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="gc analyzer not found")
    if gc.status == GCStatus.OFFLINE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="gc analyzer is offline; readings rejected",
        )

    try:
        hv = compute_heating_value(
            Composition(
                ch4_pct=payload.ch4_pct,
                c2h6_pct=payload.c2h6_pct,
                c3h8_pct=payload.c3h8_pct,
                ic4h10_pct=payload.ic4h10_pct,
                nc4h10_pct=payload.nc4h10_pct,
                n2_pct=payload.n2_pct,
                co2_pct=payload.co2_pct,
                others_pct=payload.others_pct,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    row = GCReading(
        gc_id=payload.gc_id,
        station_id=payload.station_id,
        ts=payload.ts,
        ch4_pct=payload.ch4_pct,
        c2h6_pct=payload.c2h6_pct,
        c3h8_pct=payload.c3h8_pct,
        ic4h10_pct=payload.ic4h10_pct,
        nc4h10_pct=payload.nc4h10_pct,
        n2_pct=payload.n2_pct,
        co2_pct=payload.co2_pct,
        others_pct=payload.others_pct,
        hhv_mj_nm3=hv.hhv_mj_nm3,
        lhv_mj_nm3=hv.lhv_mj_nm3,
        wobbe_mj_nm3=hv.wobbe_mj_nm3,
        density_kg_nm3=hv.density_kg_nm3,
        validity=payload.validity,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return GCReadingRead.model_validate(row)


@router.get("/gc", response_model=PagedResult[GCReadingRead])
def list_gc_readings(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
    gc_id: int | None = Query(None),
    station_id: int | None = Query(None),
    validity: Validity | None = Query(None),
    ts_from: datetime | None = Query(None),
    ts_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
) -> PagedResult[GCReadingRead]:
    stmt = select(GCReading)
    count_stmt = select(func.count()).select_from(GCReading)

    clauses = []
    if gc_id is not None:
        clauses.append(GCReading.gc_id == gc_id)
    if station_id is not None:
        clauses.append(GCReading.station_id == station_id)
    if validity is not None:
        clauses.append(GCReading.validity == validity)
    if ts_from is not None:
        clauses.append(GCReading.ts >= ts_from)
    if ts_to is not None:
        clauses.append(GCReading.ts <= ts_to)
    for c in clauses:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(GCReading.ts.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return PagedResult[GCReadingRead](
        total=total,
        page=page,
        size=size,
        items=[GCReadingRead.model_validate(r) for r in rows],
    )

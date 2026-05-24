"""计量站档案 CRUD。

权限矩阵同气源：ADMIN/METER_ENG 可写，其他只读。
关联气源时校验存在且未 RETIRED。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, get_current_user, require_meter_eng
from ..models.gas_sources import GasSource, GasSourceStatus
from ..models.metering_stations import MeteringStation, StationStatus
from ..schemas.common import PagedResult
from ..schemas.metering_stations import (
    MeteringStationCreate,
    MeteringStationRead,
    MeteringStationUpdate,
)

router = APIRouter(prefix="/api/metering-stations", tags=["metering-stations"])


def _ensure_source_alive(db, source_id: int | None) -> None:
    if source_id is None:
        return
    src = db.get(GasSource, source_id)
    if not src:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="referenced gas source not found")
    if src.status == GasSourceStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="referenced gas source has been retired",
        )


@router.get("", response_model=PagedResult[MeteringStationRead])
def list_stations(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    status_filter: StationStatus | None = Query(None, alias="status"),
    source_id: int | None = Query(None),
) -> PagedResult[MeteringStationRead]:
    stmt = select(MeteringStation)
    count_stmt = select(func.count()).select_from(MeteringStation)
    if status_filter is not None:
        stmt = stmt.where(MeteringStation.status == status_filter)
        count_stmt = count_stmt.where(MeteringStation.status == status_filter)
    if source_id is not None:
        stmt = stmt.where(MeteringStation.source_id == source_id)
        count_stmt = count_stmt.where(MeteringStation.source_id == source_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(MeteringStation.code).offset((page - 1) * size).limit(size)
    ).all()
    return PagedResult[MeteringStationRead](
        total=total,
        page=page,
        size=size,
        items=[MeteringStationRead.model_validate(r) for r in rows],
    )


@router.get("/{station_id}", response_model=MeteringStationRead)
def get_station(
    station_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> MeteringStationRead:
    obj = db.get(MeteringStation, station_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="metering station not found")
    return MeteringStationRead.model_validate(obj)


@router.post("", response_model=MeteringStationRead, status_code=status.HTTP_201_CREATED)
def create_station(
    payload: MeteringStationCreate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> MeteringStationRead:
    if db.scalar(select(MeteringStation).where(MeteringStation.code == payload.code)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"station code {payload.code} already exists",
        )
    _ensure_source_alive(db, payload.source_id)
    obj = MeteringStation(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return MeteringStationRead.model_validate(obj)


@router.patch("/{station_id}", response_model=MeteringStationRead)
def update_station(
    station_id: int,
    payload: MeteringStationUpdate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> MeteringStationRead:
    obj = db.get(MeteringStation, station_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="metering station not found")
    data = payload.model_dump(exclude_unset=True)
    if "source_id" in data:
        _ensure_source_alive(db, data["source_id"])
    if (
        "design_flow_min_nm3h" in data or "design_flow_max_nm3h" in data
    ):
        new_min = data.get("design_flow_min_nm3h", obj.design_flow_min_nm3h)
        new_max = data.get("design_flow_max_nm3h", obj.design_flow_max_nm3h)
        if float(new_max) <= float(new_min):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="design_flow_max must be greater than design_flow_min",
            )
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return MeteringStationRead.model_validate(obj)


@router.delete("/{station_id}", response_model=MeteringStationRead)
def offline_station(
    station_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> MeteringStationRead:
    """软停用：置为 OFFLINE，编号保留。"""
    obj = db.get(MeteringStation, station_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="metering station not found")
    obj.status = StationStatus.OFFLINE
    db.commit()
    db.refresh(obj)
    return MeteringStationRead.model_validate(obj)

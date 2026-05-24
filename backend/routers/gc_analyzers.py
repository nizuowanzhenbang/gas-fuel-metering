"""GC（气相色谱仪）档案 CRUD。

权限矩阵同气源：ADMIN/METER_ENG 可写，其他只读。
关联计量站时校验存在且未 OFFLINE。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, get_current_user, require_meter_eng
from ..models.gc_analyzers import GCAnalyzer, GCStatus
from ..models.metering_stations import MeteringStation, StationStatus
from ..schemas.common import PagedResult
from ..schemas.gc_analyzers import GCAnalyzerCreate, GCAnalyzerRead, GCAnalyzerUpdate

router = APIRouter(prefix="/api/gc-analyzers", tags=["gc-analyzers"])


def _ensure_station_active(db, station_id: int | None) -> None:
    if station_id is None:
        return
    st = db.get(MeteringStation, station_id)
    if not st:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="referenced station not found")
    if st.status == StationStatus.OFFLINE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="referenced station is offline",
        )


@router.get("", response_model=PagedResult[GCAnalyzerRead])
def list_gc_analyzers(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    status_filter: GCStatus | None = Query(None, alias="status"),
    station_id: int | None = Query(None),
) -> PagedResult[GCAnalyzerRead]:
    stmt = select(GCAnalyzer)
    count_stmt = select(func.count()).select_from(GCAnalyzer)
    if status_filter is not None:
        stmt = stmt.where(GCAnalyzer.status == status_filter)
        count_stmt = count_stmt.where(GCAnalyzer.status == status_filter)
    if station_id is not None:
        stmt = stmt.where(GCAnalyzer.station_id == station_id)
        count_stmt = count_stmt.where(GCAnalyzer.station_id == station_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(GCAnalyzer.code).offset((page - 1) * size).limit(size)
    ).all()
    return PagedResult[GCAnalyzerRead](
        total=total,
        page=page,
        size=size,
        items=[GCAnalyzerRead.model_validate(r) for r in rows],
    )


@router.get("/{gc_id}", response_model=GCAnalyzerRead)
def get_gc(
    gc_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> GCAnalyzerRead:
    obj = db.get(GCAnalyzer, gc_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gc analyzer not found")
    return GCAnalyzerRead.model_validate(obj)


@router.post("", response_model=GCAnalyzerRead, status_code=status.HTTP_201_CREATED)
def create_gc(
    payload: GCAnalyzerCreate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> GCAnalyzerRead:
    if db.scalar(select(GCAnalyzer).where(GCAnalyzer.code == payload.code)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"gc code {payload.code} already exists",
        )
    _ensure_station_active(db, payload.station_id)
    obj = GCAnalyzer(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return GCAnalyzerRead.model_validate(obj)


@router.patch("/{gc_id}", response_model=GCAnalyzerRead)
def update_gc(
    gc_id: int,
    payload: GCAnalyzerUpdate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> GCAnalyzerRead:
    obj = db.get(GCAnalyzer, gc_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gc analyzer not found")
    data = payload.model_dump(exclude_unset=True)
    if "station_id" in data:
        _ensure_station_active(db, data["station_id"])
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return GCAnalyzerRead.model_validate(obj)


@router.delete("/{gc_id}", response_model=GCAnalyzerRead)
def offline_gc(
    gc_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> GCAnalyzerRead:
    obj = db.get(GCAnalyzer, gc_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gc analyzer not found")
    obj.status = GCStatus.OFFLINE
    db.commit()
    db.refresh(obj)
    return GCAnalyzerRead.model_validate(obj)

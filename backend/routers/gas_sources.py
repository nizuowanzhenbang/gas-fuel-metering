"""气源档案 CRUD。

权限矩阵（CLAUDE.md）：
- 写：ADMIN / METER_ENG
- 读：所有已登录用户

软删除：DELETE 把 status 置为 RETIRED，编号永不复用。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, get_current_user, require_meter_eng
from ..models.gas_sources import GasSource, GasSourceStatus
from ..schemas.common import PagedResult
from ..schemas.gas_sources import GasSourceCreate, GasSourceRead, GasSourceUpdate

router = APIRouter(prefix="/api/gas-sources", tags=["gas-sources"])


@router.get("", response_model=PagedResult[GasSourceRead])
def list_gas_sources(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    status_filter: GasSourceStatus | None = Query(None, alias="status"),
) -> PagedResult[GasSourceRead]:
    stmt = select(GasSource)
    count_stmt = select(func.count()).select_from(GasSource)
    if status_filter is not None:
        stmt = stmt.where(GasSource.status == status_filter)
        count_stmt = count_stmt.where(GasSource.status == status_filter)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(GasSource.code).offset((page - 1) * size).limit(size)
    ).all()
    return PagedResult[GasSourceRead](
        total=total,
        page=page,
        size=size,
        items=[GasSourceRead.model_validate(r) for r in rows],
    )


@router.get("/{source_id}", response_model=GasSourceRead)
def get_gas_source(
    source_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> GasSourceRead:
    obj = db.get(GasSource, source_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gas source not found")
    return GasSourceRead.model_validate(obj)


@router.post("", response_model=GasSourceRead, status_code=status.HTTP_201_CREATED)
def create_gas_source(
    payload: GasSourceCreate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> GasSourceRead:
    if db.scalar(select(GasSource).where(GasSource.code == payload.code)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"gas source code {payload.code} already exists",
        )
    obj = GasSource(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return GasSourceRead.model_validate(obj)


@router.patch("/{source_id}", response_model=GasSourceRead)
def update_gas_source(
    source_id: int,
    payload: GasSourceUpdate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> GasSourceRead:
    obj = db.get(GasSource, source_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gas source not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return GasSourceRead.model_validate(obj)


@router.delete("/{source_id}", response_model=GasSourceRead)
def retire_gas_source(
    source_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> GasSourceRead:
    """软删除：置为 RETIRED。编号不可复用。"""
    obj = db.get(GasSource, source_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gas source not found")
    obj.status = GasSourceStatus.RETIRED
    db.commit()
    db.refresh(obj)
    return GasSourceRead.model_validate(obj)

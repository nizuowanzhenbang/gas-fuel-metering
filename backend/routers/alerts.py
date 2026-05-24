"""告警路由 —— 查询 + 状态机处置。

业务约定：
- 告警写入（POST）由 **系统内部** 触发：调度器扫描、对账失败、跨系统回调等
  这里仍开放 POST 给 ADMIN/METER_ENG 用，作为人工补录通道；普通业务路径走 services 层 helper。
- 状态机：OPEN → ACKED → RESOLVED；不可逆向
- 处置权限：所有"非 VIEWER"角色都可以 ack/resolve（一线运行人员发现问题先认领）
- 编号：AL-YYYYMMDD-NNNN，由 utils.numbering.next_alert_no 在事务内生成
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, Role, get_current_user, require_meter_eng, require_roles
from ..models.alerts import Alert, AlertCategory, AlertLevel, AlertStatus
from ..models.users import User
from ..schemas.alerts import AlertCreate, AlertRead
from ..schemas.common import PagedResult
from ..utils.numbering import next_alert_no

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

require_dispatcher = require_roles(Role.ADMIN, Role.METER_ENG, Role.OPERATOR, Role.ACCOUNTANT)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_user_id(db, username: str) -> int | None:
    return db.scalar(select(User.id).where(User.username == username))


@router.get("", response_model=PagedResult[AlertRead])
def list_alerts(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
    level: AlertLevel | None = Query(None),
    category: AlertCategory | None = Query(None),
    status_filter: AlertStatus | None = Query(None, alias="status"),
    station_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
) -> PagedResult[AlertRead]:
    stmt = select(Alert)
    count_stmt = select(func.count()).select_from(Alert)
    clauses = []
    if level is not None:
        clauses.append(Alert.level == level)
    if category is not None:
        clauses.append(Alert.category == category)
    if status_filter is not None:
        clauses.append(Alert.status == status_filter)
    if station_id is not None:
        clauses.append(Alert.station_id == station_id)
    for c in clauses:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Alert.opened_at.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return PagedResult[AlertRead](
        total=total,
        page=page,
        size=size,
        items=[AlertRead.model_validate(r) for r in rows],
    )


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(
    alert_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> AlertRead:
    obj = db.get(Alert, alert_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    return AlertRead.model_validate(obj)


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: AlertCreate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_meter_eng)],
) -> AlertRead:
    obj = Alert(
        alert_no=next_alert_no(db),
        level=payload.level,
        category=payload.category,
        message=payload.message,
        station_id=payload.station_id,
        gc_id=payload.gc_id,
        source_id=payload.source_id,
        payload_json=payload.payload_json,
        status=AlertStatus.OPEN,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return AlertRead.model_validate(obj)


@router.post("/{alert_id}/ack", response_model=AlertRead)
def acknowledge_alert(
    alert_id: int,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(require_dispatcher)],
) -> AlertRead:
    obj = db.get(Alert, alert_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    if obj.status != AlertStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"alert in status {obj.status} cannot be acknowledged",
        )
    obj.status = AlertStatus.ACKED
    obj.acked_by = _resolve_user_id(db, current.username)
    obj.acked_at = _utcnow()
    db.commit()
    db.refresh(obj)
    return AlertRead.model_validate(obj)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
def resolve_alert(
    alert_id: int,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(require_dispatcher)],
) -> AlertRead:
    obj = db.get(Alert, alert_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    if obj.status == AlertStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="alert already resolved",
        )
    obj.status = AlertStatus.RESOLVED
    obj.resolved_by = _resolve_user_id(db, current.username)
    obj.resolved_at = _utcnow()
    # 如果还未认领，resolve 同时回填 acked 信息，保持审计链路完整
    if obj.acked_at is None:
        obj.acked_by = obj.resolved_by
        obj.acked_at = obj.resolved_at
    db.commit()
    db.refresh(obj)
    return AlertRead.model_validate(obj)

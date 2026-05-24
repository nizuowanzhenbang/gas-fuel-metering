"""告警写入工具。

调度任务、对账失败、跨系统回调等内部场景统一走这里写告警，
避免重复实现编号生成与去重逻辑。

去重策略：同一 (category, station_id|gc_id|source_id, status=OPEN) 视为同一未处置告警，
重复触发只更新 payload_json 与 message，不再新开单。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models.alerts import Alert, AlertCategory, AlertLevel, AlertStatus
from ..utils.numbering import next_alert_no

logger = logging.getLogger(__name__)


def emit_alert(
    db: Session,
    *,
    level: AlertLevel,
    category: AlertCategory,
    message: str,
    station_id: int | None = None,
    gc_id: int | None = None,
    source_id: int | None = None,
    payload_json: dict[str, Any] | None = None,
) -> Alert:
    """写或合并一条未处置告警。"""
    dedup_clauses = [
        Alert.category == category,
        Alert.status == AlertStatus.OPEN,
    ]
    if station_id is not None:
        dedup_clauses.append(Alert.station_id == station_id)
    if gc_id is not None:
        dedup_clauses.append(Alert.gc_id == gc_id)
    if source_id is not None:
        dedup_clauses.append(Alert.source_id == source_id)

    existing = db.scalar(select(Alert).where(and_(*dedup_clauses)).limit(1))
    if existing:
        existing.message = message
        existing.level = level  # 升降级允许覆盖
        if payload_json is not None:
            existing.payload_json = payload_json
        db.commit()
        db.refresh(existing)
        return existing

    alert = Alert(
        alert_no=next_alert_no(db),
        level=level,
        category=category,
        message=message,
        station_id=station_id,
        gc_id=gc_id,
        source_id=source_id,
        payload_json=payload_json,
        status=AlertStatus.OPEN,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert

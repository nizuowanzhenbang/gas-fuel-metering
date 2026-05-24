"""告警 schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models.alerts import AlertCategory, AlertLevel, AlertStatus


class AlertCreate(BaseModel):
    """系统内部 / 调度任务用，外部不直接暴露写入。"""

    level: AlertLevel
    category: AlertCategory
    message: str = Field(min_length=1, max_length=512)
    station_id: int | None = None
    gc_id: int | None = None
    source_id: int | None = None
    payload_json: dict[str, Any] | None = None


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_no: str
    level: AlertLevel
    category: AlertCategory
    status: AlertStatus
    message: str
    station_id: int | None
    gc_id: int | None
    source_id: int | None
    payload_json: dict[str, Any] | None
    opened_at: datetime
    acked_by: int | None
    acked_at: datetime | None
    resolved_by: int | None
    resolved_at: datetime | None

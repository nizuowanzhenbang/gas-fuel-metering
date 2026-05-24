from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class AlertCategory(StrEnum):
    METER_OFFLINE = "METER_OFFLINE"
    PT_OUT_OF_RANGE = "PT_OUT_OF_RANGE"
    PRIMARY_BACKUP_DEVIATION = "PRIMARY_BACKUP_DEVIATION"  # 主备偏差 > 0.3%
    RECONCILE_OVERSHOOT = "RECONCILE_OVERSHOOT"
    GC_FAULT = "GC_FAULT"
    GC_CALIBRATION_DUE = "GC_CALIBRATION_DUE"
    METER_VERIFICATION_DUE = "METER_VERIFICATION_DUE"
    NETWORK_PRESSURE_ANOMALY = "NETWORK_PRESSURE_ANOMALY"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKED = "ACKED"
    RESOLVED = "RESOLVED"


class Alert(Base):
    """告警台账，编号 AL-YYYYMMDD-NNNN。"""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    level: Mapped[AlertLevel] = mapped_column(String(16))
    category: Mapped[AlertCategory] = mapped_column(String(32), index=True)

    station_id: Mapped[int | None] = mapped_column(ForeignKey("metering_stations.id"), nullable=True)
    gc_id: Mapped[int | None] = mapped_column(ForeignKey("gc_analyzers.id"), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("gas_sources.id"), nullable=True)

    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[AlertStatus] = mapped_column(String(16), default=AlertStatus.OPEN)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    acked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

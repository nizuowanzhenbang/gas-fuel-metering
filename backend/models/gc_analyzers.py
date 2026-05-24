from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GCStatus(StrEnum):
    RUNNING = "RUNNING"
    CALIBRATING = "CALIBRATING"
    FAULT = "FAULT"
    OFFLINE = "OFFLINE"


class GCAnalyzer(Base):
    """气相色谱仪档案，编号 GC-NN。"""

    __tablename__ = "gc_analyzers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    model: Mapped[str] = mapped_column(String(64))
    serial_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    station_id: Mapped[int | None] = mapped_column(ForeignKey("metering_stations.id"), nullable=True)

    last_calibration_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_calibration_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[GCStatus] = mapped_column(String(16), default=GCStatus.RUNNING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

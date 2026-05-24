from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Validity(StrEnum):
    """时序读数有效性标记，与 emission-monitoring 字段语义保持一致。"""

    VALID = "VALID"
    CALIBRATING = "CALIBRATING"
    FAULT = "FAULT"
    SUBSTITUTE = "SUBSTITUTE"  # 替代值（人工补录或公式回算）


class MeteringSource(StrEnum):
    PRIMARY = "PRIMARY"
    BACKUP = "BACKUP"


class MeteringReading(Base):
    """计量站分钟级时序读数。"""

    __tablename__ = "metering_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("metering_stations.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    actual_volume_rate_m3h: Mapped[float] = mapped_column(Numeric(12, 3))
    normal_volume_rate_nm3h: Mapped[float] = mapped_column(Numeric(12, 3))
    pressure_kpa: Mapped[float] = mapped_column(Numeric(10, 2))
    temperature_c: Mapped[float] = mapped_column(Numeric(6, 1))
    accumulated_volume_nm3: Mapped[float] = mapped_column(Numeric(16, 3))

    validity: Mapped[Validity] = mapped_column(String(16), default=Validity.VALID)
    source: Mapped[MeteringSource] = mapped_column(String(8), default=MeteringSource.PRIMARY)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_metering_readings_station_ts", "station_id", "ts"),
    )

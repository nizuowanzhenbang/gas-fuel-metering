from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StationStatus(StrEnum):
    RUNNING = "RUNNING"
    MAINTENANCE = "MAINTENANCE"
    OFFLINE = "OFFLINE"


class MeteringStation(Base):
    """计量站档案，编号 MS-NN。"""

    __tablename__ = "metering_stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("gas_sources.id"), nullable=True)

    design_pressure_kpa: Mapped[float] = mapped_column(Numeric(10, 2))
    design_flow_min_nm3h: Mapped[float] = mapped_column(Numeric(12, 3))
    design_flow_max_nm3h: Mapped[float] = mapped_column(Numeric(12, 3))

    # 法定计量器具检定到期日。早于 30 天进入预警。
    verified_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[StationStatus] = mapped_column(String(16), default=StationStatus.RUNNING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

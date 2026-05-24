from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GasType(StrEnum):
    PIPELINE = "PIPELINE"  # 管道气
    LNG = "LNG"            # LNG 气化


class GasSourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class GasSource(Base):
    """气源档案，编号 SRC-NNN。"""

    __tablename__ = "gas_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    supplier: Mapped[str] = mapped_column(String(64))  # 中石油 / 中石化 / 中海油 / LNG 接收站
    gas_type: Mapped[GasType] = mapped_column(String(16))
    contract_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contract_base_price: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)  # 元/Nm³
    daily_volume_plan_nm3: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)
    status: Mapped[GasSourceStatus] = mapped_column(String(16), default=GasSourceStatus.ACTIVE)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

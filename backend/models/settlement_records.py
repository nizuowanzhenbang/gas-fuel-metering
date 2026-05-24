from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SettlementStatus(StrEnum):
    DRAFT = "DRAFT"
    RECONCILED = "RECONCILED"
    APPROVED = "APPROVED"
    SETTLED = "SETTLED"
    ARCHIVED = "ARCHIVED"


class SettlementRecord(Base):
    """月结算单。编号 SETTLE-YYYYMM-NN。"""

    __tablename__ = "settlement_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("gas_sources.id"))

    period_start: Mapped[datetime] = mapped_column(Date)
    period_end: Mapped[datetime] = mapped_column(Date)

    plant_volume_nm3: Mapped[float] = mapped_column(Numeric(16, 3))
    upstream_volume_nm3: Mapped[float | None] = mapped_column(Numeric(16, 3), nullable=True)
    diff_pct: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)

    avg_hhv_mj_nm3: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    total_energy_gj: Mapped[float | None] = mapped_column(Numeric(16, 3), nullable=True)

    contract_price: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)

    status: Mapped[SettlementStatus] = mapped_column(String(16), default=SettlementStatus.DRAFT)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

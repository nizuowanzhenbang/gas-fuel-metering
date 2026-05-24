from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .metering_readings import Validity


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GCReading(Base):
    """GC 在线组分读数。摩尔百分比单位，sum 约等于 100。"""

    __tablename__ = "gc_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    gc_id: Mapped[int] = mapped_column(ForeignKey("gc_analyzers.id"), index=True)
    station_id: Mapped[int | None] = mapped_column(ForeignKey("metering_stations.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    ch4_pct: Mapped[float] = mapped_column(Numeric(7, 4))
    c2h6_pct: Mapped[float] = mapped_column(Numeric(7, 4), default=0)
    c3h8_pct: Mapped[float] = mapped_column(Numeric(7, 4), default=0)
    ic4h10_pct: Mapped[float] = mapped_column(Numeric(7, 4), default=0)
    nc4h10_pct: Mapped[float] = mapped_column(Numeric(7, 4), default=0)
    n2_pct: Mapped[float] = mapped_column(Numeric(7, 4), default=0)
    co2_pct: Mapped[float] = mapped_column(Numeric(7, 4), default=0)
    others_pct: Mapped[float] = mapped_column(Numeric(7, 4), default=0)

    hhv_mj_nm3: Mapped[float] = mapped_column(Numeric(8, 3))
    lhv_mj_nm3: Mapped[float] = mapped_column(Numeric(8, 3))
    wobbe_mj_nm3: Mapped[float] = mapped_column(Numeric(8, 3))
    density_kg_nm3: Mapped[float] = mapped_column(Numeric(8, 4))

    validity: Mapped[Validity] = mapped_column(String(16), default=Validity.VALID)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_gc_readings_gc_ts", "gc_id", "ts"),
    )

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ReconciliationRun(Base):
    """Append-only through the API; no cascading link to mutable metering tables."""
    __tablename__ = 'reconciliation_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey('reconciliation_runs.id'), index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(128))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))

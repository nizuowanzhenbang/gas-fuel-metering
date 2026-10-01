"""共享的计量质量检查：API、Excel 和调度器使用同一聚合规则。"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select

from .business_day import current_policy
from ..models.metering_readings import MeteringReading, MeteringSource, Validity
from ..models.metering_stations import MeteringStation


class MeteringEvidence(BaseModel):
    station_id: int
    source: str
    sample_count: int
    excluded_count: int
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    start_counter_nm3: float | None = None
    end_counter_nm3: float | None = None
    volume_nm3: float | None = None
    issues: list[str] = Field(default_factory=list)


class DataQualityError(ValueError):
    def __init__(self, evidence: list[MeteringEvidence]):
        self.evidence = evidence
        reason = '; '.join(f'{e.station_id}/{e.source}: {", ".join(e.issues)}' for e in evidence if e.issues)
        super().__init__(f'计量数据需核对，未生成对账结论：{reason}')

    def detail(self):
        return {'code': 'METERING_DATA_QUALITY', 'message': str(self),
                'stations': [e.model_dump(mode='json') for e in self.evidence]}


def as_utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def day_window(day: date) -> tuple[datetime, datetime]:
    window = current_policy().window(day)
    return window.start_utc, window.end_utc


def station_evidence(db, station_id, source, start, end, *, full_day=False) -> MeteringEvidence:
    rows = db.execute(select(MeteringReading.ts, MeteringReading.accumulated_volume_nm3, MeteringReading.validity)
        .where(MeteringReading.station_id == station_id, MeteringReading.source == source,
               MeteringReading.ts >= start, MeteringReading.ts <= end)
        .order_by(MeteringReading.ts, MeteringReading.id)).all()
    valid = [r for r in rows if r.validity == Validity.VALID]
    evidence = MeteringEvidence(station_id=station_id, source=source,
                               sample_count=len(valid), excluded_count=len(rows) - len(valid))
    if len(valid) < 2:
        evidence.issues.append('INSUFFICIENT_SAMPLES')
    if not valid:
        return evidence
    evidence.first_ts, evidence.last_ts = as_utc(valid[0].ts), as_utc(valid[-1].ts)
    counters = [Decimal(str(r.accumulated_volume_nm3)) for r in valid]
    if any(not v.is_finite() or v < 0 for v in counters):
        evidence.issues.append('INVALID_COUNTER')
    else:
        evidence.start_counter_nm3, evidence.end_counter_nm3 = float(counters[0]), float(counters[-1])
        if any(b < a for a, b in zip(counters, counters[1:])):
            evidence.issues.append('COUNTER_ROLLBACK')
    if len({as_utc(r.ts) for r in valid}) != len(valid):
        evidence.issues.append('DUPLICATE_TIMESTAMP')
    if full_day and (evidence.first_ts != as_utc(start) or evidence.last_ts != as_utc(end)):
        evidence.issues.append('INCOMPLETE_DAY')
    if not evidence.issues:
        evidence.volume_nm3 = float(counters[-1] - counters[0])
    return evidence


def source_daily_volume(db, source_id: int, business_date: date):
    start, end = day_window(business_date)
    stations = db.scalars(select(MeteringStation).where(MeteringStation.source_id == source_id)
                          .order_by(MeteringStation.id)).all()
    if not stations:
        raise ValueError('gas source has no metering stations bound; nothing to reconcile')
    evidence = [station_evidence(db, st.id, MeteringSource.PRIMARY, start, end, full_day=True) for st in stations]
    if any(e.issues for e in evidence):
        raise DataQualityError(evidence)
    total = sum((Decimal(str(e.volume_nm3)) for e in evidence), Decimal(0))
    return float(total), sum(e.sample_count for e in evidence), evidence


def dual_loop_volume(db, station_id, start, end, *, full_day=False):
    evidence = [station_evidence(db, station_id, source, start, end, full_day=full_day)
                for source in (MeteringSource.PRIMARY, MeteringSource.BACKUP)]
    primary, backup = evidence
    if not any(e.issues for e in evidence):
        if (primary.first_ts, primary.last_ts) != (backup.first_ts, backup.last_ts):
            for e in evidence:
                e.issues.append('MISALIGNED_LOOPS')
                e.volume_nm3 = None
    if any(e.issues for e in evidence):
        raise DataQualityError(evidence)
    return primary, backup
